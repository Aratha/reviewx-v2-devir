import asyncio
import ipaddress
import json
import logging
import os
import re
import socket
import ssl
import time
from urllib.parse import urlparse
from typing import Any

import certifi
import httpx



from config import get_settings, resolved_llm_model

from models.schemas import RuleCheckItem, ViolationItem

from services.rules_store import (
    RuleBundle,
    RuleLine,
    get_rule_line,
    iter_rule_ids_ordered,
    published_bundle,
)

from services.llm_log import append_entry, log_timestamp_iso, new_log_id


logger = logging.getLogger(__name__)


def _llm_ssl_context() -> ssl.SSLContext:
    """trust_env=False iken httpx SSL_CERT_FILE'ı yok sayıp certifi kullanır; kurum kök CA'sı
    imajın sistem deposunda olduğundan SSL_CERT_FILE açıkça okunur (yoksa certifi)."""
    return ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE") or certifi.where())


def _is_private_or_tailscale_ip(ip_text: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError:
        return False
    # RFC1918 + loopback/link-local + ULA + Tailscale CGNAT (100.64.0.0/10)
    if ip.is_private or ip.is_loopback or ip.is_link_local:
        return True
    return ip in ipaddress.ip_network("100.64.0.0/10")


def _enforce_llm_network_policy(settings, url: str) -> None:
    if not bool(getattr(settings, "llm_enforce_private_network", True)):
        return
    parsed = urlparse(url)
    host = (parsed.hostname or "").strip()
    if not host:
        raise ValueError("LLM URL host çözümlenemedi.")

    allow_raw = str(getattr(settings, "llm_allow_public_hosts", "") or "")
    allow_hosts = {h.strip().lower() for h in allow_raw.split(",") if h.strip()}
    if host.lower() in allow_hosts:
        return

    # Host doğrudan IP ise doğrudan kontrol et.
    if _is_private_or_tailscale_ip(host):
        return
    try:
        ipaddress.ip_address(host)
        raise ValueError(
            f"LLM hedefi private/Tailscale ağında değil: {host}. "
            "Kurumsal politika gereği cloud/public çıkış engellendi."
        )
    except ValueError:
        # hostname ise resolve edilen tüm IP'ler private/tailscale olmalı.
        pass

    try:
        infos = socket.getaddrinfo(host, parsed.port or 80, proto=socket.IPPROTO_TCP)
    except OSError as e:
        raise ValueError(f"LLM host DNS çözümlenemedi: {host} ({e})") from e
    ips: set[str] = set()
    for info in infos:
        sockaddr = info[4]
        if sockaddr and len(sockaddr) >= 1:
            ips.add(str(sockaddr[0]))
    if not ips:
        raise ValueError(f"LLM host için IP çözümlenemedi: {host}")
    bad = [ip for ip in ips if not _is_private_or_tailscale_ip(ip)]
    if bad:
        raise ValueError(
            f"LLM hedefi public IP'ye çözülüyor ({', '.join(sorted(bad))}). "
            "Kurumsal politika gereği cloud/public çıkış engellendi."
        )


def _loads_llm_json(text: str) -> Any:
    """LLM çıktısı: string alanlarında kaçışsız satır sonu / kontrol karakterleri olabilir; strict=False ile çöz."""
    return json.loads(text, strict=False)


def _loads_llm_json_first(text: str) -> Any:
    """Metindeki ilk JSON değerini ayrıştırır (model JSON sonrası açıklama ekleyince Extra data oluşmaz)."""
    s = text.strip()
    if not s:
        raise json.JSONDecodeError("Expecting value", s, 0)
    if s.startswith("\ufeff"):
        s = s.lstrip("\ufeff").strip()
    dec = json.JSONDecoder()
    # Bazı modeller yanıt içinde örnek JSON'lar veya backtick içinde geçersiz JSON parçaları ekleyebilir.
    # Bu durumda ilk "{" / "[" gerçek çıktı olmayabilir; bu yüzden tüm aday başlangıçları dene.
    starts: list[int] = []
    for j, ch in enumerate(s):
        if ch == "{" or ch == "[":
            starts.append(j)
    if not starts:
        raise json.JSONDecodeError("Expecting value", s, 0)
    last_err: json.JSONDecodeError | None = None
    for i in starts:
        try:
            return dec.raw_decode(s, i)[0]
        except json.JSONDecodeError as e:
            last_err = e
            continue
    assert last_err is not None
    raise last_err


def _try_loads_llm_json_first(text: str) -> object | None:
    try:
        return _loads_llm_json_first(text)
    except json.JSONDecodeError:
        return None


def _coerce_violations_list_value(val: object) -> list | None:
    """violations alanı liste veya JSON dizi metni olabilir."""
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return []
        try:
            parsed = _loads_llm_json_first(s)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, list) else None
    return None


def _mini_bundle_for_rule(line: RuleLine, tier: str) -> RuleBundle:
    """Tek kural için parse_review_response ile uyumlu mini bundle."""
    if tier == "critical":
        return RuleBundle(critical=[line], normal=[])
    return RuleBundle(critical=[], normal=[line])



SYSTEM_PROMPT = """Sen bir code-review kural denetleyicisisin.

Görevin:
Verilen kodu yalnızca verilen kural/kurallar açısından değerlendirip ihlal varsa raporlamak.

GENEL DAVRANIŞ KURALLARI (ÇOK KRİTİK):

1. Sadece gerçek ihlalleri raporla.
2. İhlal yoksa veya emin değilsen: yanıtta yalnızca {"violations": []} kullan (tamamen boş metin, sadece boşluk veya “sessiz kalma” yasak — arka uç yalnızca JSON okur).
3. 'İhlal yok', 'uygun', 'kural dışı', 'bilgi', 'yorum', 'öneri' gibi serbest metin üretme (bunlar JSON dışında veya violations içinde açıklama olarak yasak).
4. Kural kapsamına girmeyen hiçbir kullanım hakkında violations’a kayıt ekleme.
5. Best practice, performans, optimizasyon veya öneri yapma.
6. Gereksiz veya eksik kullanım hakkında yorum yapma, eğer kural bunu açıkça istemiyorsa.
7. Bir kullanım ihlal değilse tamamen yok say.
8. Çıktı üretme eşiğin yüksek olmalı: açık ve net ihlal yoksa violations boş dizi.
9. Yalnızca verilen kuralın açıkça tanımladığı ihlalleri değerlendir; kural dışı analiz yapma.
10. Kodun genel kalitesi hakkında yorum yapma.

KARAR PRENSİBİ:
- 'Şüpheli' veya 'olabilir' durumlar ihlal değildir.
- Sadece kesin ve net ihlaller violations içinde raporlanır.

ZORUNLU ÇIKTI SÖZLEŞMESİ — BU BLOK EN YÜKSEK ÖNCELİK (İngilizce özet aynı anlamda geçerlidir):

The API consumer parses your reply with a JSON parser. Violating any bullet makes the response unusable.

1) Reply MUST be exactly one JSON value: one root object. No array as root. No text before or after the JSON.
2) First non-whitespace character MUST be "{" . Last character that closes the value MUST be "}" .
3) Forbidden: markdown fences (```), labels like "JSON:", "Output:", "Sure,", XML/HTML, <think> blocks, bullet lists outside JSON, any prose after the closing brace.
4) Root object MUST have exactly one property: "violations" (lowercase). Do not add "status", "summary", "result", "message", "notes", or other top-level keys.
5) "violations" MUST be a JSON array (possibly empty). Never a string. Never null unless you output {"violations": []} only — prefer empty array [].
6) Each element of "violations" MUST be one JSON object with at least: "rule_code" (string), "snippet" (string), "reason" (string). Include "object_name" (string, may be "") when applicable.
7) Do not wrap the JSON in quotes as a whole. Do not double-encode the entire response as a string.

TEKNİK NOT:
- Kullanıcı mesajında «KATALOG METADATASI» varsa şema doğrulaması için SQL ile birlikte kullan.

reason/snippet ALANLARI (ÇOK KRİTİK):
- Her violations öğesi yalnızca GERÇEK bir ihlali temsil eder.
- "reason" yalnızca ihlalin kısa nedenini yazar.
- "reason" veya "snippet" içinde ihlal olmadığını anlatan cümleler yazma.
- İhlal yoksa violations dizisine hiç öğe ekleme.

Şema (örnek — ihlal yoksa violations boş dizi):

{
  "violations": [
    {
      "rule_code": "<rule_code>",
      "object_name": "",
      "snippet": "<exact SQL>",
      "reason": "<kısa neden>"
    }
  ]
}"""


USER_PROMPT_TEMPLATE_SINGLE = """Aşağıdaki SQL kodunu verilen kural tanımına göre analiz et.

KURAL KODU (bu istekte tek kural; rule_code alanında aynen kullan):
{rule_id}

KURAL TANIMI:
{rule_text}

{sql_scope_notice}{metadata_block}ANALİZ EDİLECEK SQL:
{numbered_sql}

DEĞERLENDİRME:
- Sadece gerçek ihlalleri violations dizisine yaz; şüphede ihlal yok say.
- Kural kapsamı dışındaysa veya ihlal yoksa: {{"violations": []}}
- "reason"/"snippet" içinde ihlal olmadığını anlatan metin yazma.

ÇIKTI — SABİT FORMAT (başka hiçbir şey yazma):
- Yanıtın tamamı tek bir JSON nesnesi; kökte yalnızca "violations" anahtarı.
- Markdown (```), ön yüz metni, "İşte JSON", İngilizce özet vb. YASAK.
- İhlal varsa öğede şu alanlar zorunlu: rule_code="{rule_id}", snippet, reason; object_name gerekmezse "" olabilir.
- İsteğe bağlı: line_reference ve line_numbers (numaralı SQL ile uyumlu L… satırları).

İhlal yok örneği (tek satır, birebir bu yapı):
{{"violations":[]}}

İhlal var örnek şablon (rule_code mutlaka "{rule_id}"):
{{
  "violations": [
    {{
      "rule_code": "{rule_id}",
      "object_name": "",
      "snippet": "<SQL parçası>",
      "reason": "<kısa neden>",
      "line_reference": "L001",
      "line_numbers": [1]
    }}
  ]
}}"""


def _numbered_sql(sql: str, start_line: int = 1) -> str:
    """SQL metnini L001 / L002 biçiminde satır numaralarıyla döndürür (start_line: orijinal dosyada ilk satır no)."""
    if not sql:
        return ""
    lines = sql.splitlines()
    n = len(lines)
    last_no = start_line + n - 1
    width = max(3, len(str(last_no)))
    return "\n".join(
        f"L{i:0{width}d}  {line}" for i, line in enumerate(lines, start=start_line)
    )


def _split_sql_into_two_parts(sql: str) -> tuple[str, str, int]:
    """SQL'i iki parçaya böler; dönüş: (parça1, parça2, parça2'nin ilk satır numarası 1 tabanlı).

    Çok satırlıda satır ortasından; tek satırda karakter ortasından böler (aynı satır no iki istekte
    ayrı açıklanır).
    """
    if not sql:
        return "", "", 1
    lines = sql.splitlines()
    n = len(lines)
    if n >= 2:
        mid = max(1, n // 2)
        part1 = "\n".join(lines[:mid])
        part2 = "\n".join(lines[mid:])
        return part1, part2, mid + 1
    mid_c = max(1, len(sql) // 2)
    return sql[:mid_c], sql[mid_c:], 1


def _two_part_scope_notices(sql: str, line_start_b: int) -> tuple[str, str]:
    """Parça 1 ve 2 için kullanıcı mesajına eklenecek uyarı metinleri."""
    lines = sql.splitlines()
    n = len(lines)
    if n >= 2:
        total = n
        end1 = line_start_b - 1
        n1 = (
            f"ÖNEMLİ — PARÇA 1/2: Aşağıdaki kod yalnızca nesnenin satır 1–{end1} bölümüdür (toplam {total} satır). "
            "Kuralı yalnızca bu parçaya uygula; parça 2’deki kodu varsayma veya birleştirerek yorumlama.\n\n"
        )
        n2 = (
            f"ÖNEMLİ — PARÇA 2/2: Aşağıdaki kod yalnızca nesnenin satır {line_start_b}–{total} bölümüdür (toplam {total} satır). "
            "Kuralı yalnızca bu parçaya uygula; parça 1’deki kodu varsayma.\n\n"
        )
        return n1, n2
    n1 = (
        "ÖNEMLİ — PARÇA 1/2: Aşağıdaki metin orijinal tek satırın (veya tek parçanın) ilk yarısıdır. "
        "Kuralı yalnızca bu metne uygula.\n\n"
    )
    n2 = (
        "ÖNEMLİ — PARÇA 2/2: Aşağıdaki metin aynı satırın/parçanın devamıdır. "
        "Kuralı yalnızca bu metne uygula.\n\n"
    )
    return n1, n2


def _merge_two_part_single_rule(
    rid: str,
    tier: str,
    *,
    err_a: str | None,
    raw_a: str | None,
    err_b: str | None,
    raw_b: str | None,
    mini: RuleBundle,
    source_sql: str,
) -> tuple[RuleCheckItem, list[ViolationItem], str | None]:
    """Aynı kural için iki parça yanıtını tek sonuçta birleştirir."""
    partial_note = ""

    def _parse(raw: str | None) -> tuple[list[RuleCheckItem], list[ViolationItem], str | None]:
        if not raw or not raw.strip():
            return [], [], None
        return parse_review_response(raw, mini, source_sql=source_sql)

    if err_a and err_b:
        msg = f"Parça 1/2: {err_a}; Parça 2/2: {err_b}"
        return (
            RuleCheckItem(
                rule_id=rid,
                tier=tier,
                status="UNKNOWN",
                description=_brief_llm_error_for_ui(msg) if _is_llm_connection_error_msg(msg) else msg[:2000],
            ),
            [],
            msg,
        )

    if err_a:
        partial_note = "Parça 1/2 LLM isteği başarısız; yalnızca parça 2 değerlendirildi."
        checks_b, viol_b, warn_b = _parse(raw_b)
        if not checks_b:
            return (
                RuleCheckItem(
                    rule_id=rid,
                    tier=tier,
                    status="UNKNOWN",
                    description=(err_a[:1500] + " " + (warn_b or "")).strip(),
                ),
                [],
                f"{partial_note} {err_a}",
            )
        rc = checks_b[0]
        w = "; ".join(x for x in (warn_b, partial_note) if x)
        return rc, viol_b, w or None

    if err_b:
        partial_note = "Parça 2/2 LLM isteği başarısız; yalnızca parça 1 değerlendirildi."
        checks_a, viol_a, warn_a = _parse(raw_a)
        if not checks_a:
            return (
                RuleCheckItem(
                    rule_id=rid,
                    tier=tier,
                    status="UNKNOWN",
                    description=(err_b[:1500] + " " + (warn_a or "")).strip(),
                ),
                [],
                f"{partial_note} {err_b}",
            )
        rc = checks_a[0]
        w = "; ".join(x for x in (warn_a, partial_note) if x)
        return rc, viol_a, w or None

    checks_a, viol_a, warn_a = _parse(raw_a)
    checks_b, viol_b, warn_b = _parse(raw_b)

    if not checks_a and not checks_b:
        w = "; ".join(x for x in (warn_a, warn_b) if x)
        return (
            RuleCheckItem(
                rule_id=rid,
                tier=tier,
                status="UNKNOWN",
                description=w or "Çözümleme sonucu boş.",
            ),
            [],
            w,
        )
    if not checks_a:
        return checks_b[0], viol_b, warn_b
    if not checks_b:
        return checks_a[0], viol_a, warn_a

    st_a = checks_a[0].status
    st_b = checks_b[0].status
    merged_viol = list(viol_a) + list(viol_b)

    warns: list[str] = []
    if warn_a:
        warns.append(warn_a)
    if warn_b:
        warns.append(warn_b)

    if merged_viol:
        # İki parçada da aynı ihlal tekrarlanırsa (seyrek): snippet+reason ile kabaca ayıkla
        seen: set[tuple[str, str]] = set()
        deduped: list[ViolationItem] = []
        for v in merged_viol:
            key = (v.code_snippet[:200], v.description[:200])
            if key in seen:
                continue
            seen.add(key)
            deduped.append(v)
        merged_viol = deduped

    if merged_viol:
        first = merged_viol[0]
        rc = RuleCheckItem(
            rule_id=rid,
            tier=tier,
            status="FAIL",
            severity=first.severity or ("HIGH" if tier == "critical" else "LOW"),
            decision_basis="direct_evidence",
            description=(first.description or "İhlal tespit edildi.")[:500],
            line_reference=first.line_reference,
            code_snippet=first.code_snippet[:500],
        )
        w_out = "; ".join(warns) if warns else None
        return rc, merged_viol, w_out

    if st_a == "UNKNOWN" or st_b == "UNKNOWN":
        desc = checks_a[0].description or checks_b[0].description
        return (
            RuleCheckItem(
                rule_id=rid,
                tier=tier,
                status="UNKNOWN",
                description=desc,
            ),
            [],
            "; ".join(warns) if warns else None,
        )

    if st_a == "FAIL" or st_b == "FAIL":
        # İhlal listesi boş ama model FAIL dedi (seyrek): daha güvenli olanı seç
        pick = checks_a[0] if st_a == "FAIL" else checks_b[0]
        return pick, [], "; ".join(warns) if warns else None

    if st_a == "NOT_APPLICABLE" and st_b == "NOT_APPLICABLE":
        return checks_a[0], [], "; ".join(warns) if warns else None

    # PASS / NOT_APPLICABLE karışımı: ihlal yoksa PASS
    return (
        RuleCheckItem(
            rule_id=rid,
            tier=tier,
            status="PASS",
            severity="",
            decision_basis="",
            description="İhlal bulunmadı.",
            line_reference="",
            code_snippet="",
        ),
        [],
        "; ".join(warns) if warns else None,
    )


def _format_line_range(nums: list[int]) -> str:
    if not nums:
        return ""
    u = sorted(set(nums))
    if len(u) == 1:
        return f"Satır {u[0]}"
    if u == list(range(u[0], u[-1] + 1)):
        return f"Satır {u[0]}–{u[-1]}"
    return "Satır " + ", ".join(str(x) for x in u)


def _infer_line_reference_from_snippet(source_sql: str, snippet: str) -> str:
    """Kaynak SQL satırlarında snippet ile eşleşen satır veya aralık (1 tabanlı)."""
    if not source_sql or not (snippet or "").strip():
        return ""
    lines = source_sql.splitlines()
    if not lines:
        return ""
    snippet = snippet.strip()
    snip_lines = [sl.strip() for sl in snippet.splitlines() if sl.strip()]
    if not snip_lines:
        return ""
    found: list[int] = []
    for target in snip_lines[:5]:
        t = re.sub(r"\s+", " ", target)
        if len(t) < 6:
            continue
        for i, line in enumerate(lines, start=1):
            l = re.sub(r"\s+", " ", line.strip())
            if t in l or (len(t) > 12 and t[:48] in l):
                found.append(i)
                break
    if not found:
        t = re.sub(r"\s+", " ", snippet)
        if len(t) >= 12:
            head = t[: min(80, len(t))]
            for i, line in enumerate(lines, start=1):
                l = re.sub(r"\s+", " ", line.strip())
                if head in l or head[:40] in l:
                    found.append(i)
                    break
    if not found:
        return ""
    lo, hi = min(found), max(found)
    if lo == hi:
        return f"Satır {lo}"
    return f"Satır {lo}–{hi}"


def _normalize_line_ref_display(s: str) -> str:
    """L012 / L012–L015 biçimini arayüz için Satır … metnine çevirir; aksi halde aynı bırakır."""
    t = s.strip()
    if not t:
        return ""
    m = re.match(r"^L\s*0*(\d+)\s*[–-]\s*L?\s*0*(\d+)$", t, re.I)
    if m:
        return f"Satır {int(m.group(1))}–{int(m.group(2))}"
    m = re.match(r"^L\s*0*(\d+)$", t, re.I)
    if m:
        return f"Satır {int(m.group(1))}"
    return t


def _line_ref_from_violation_item(
    item: dict,
    source_sql: str | None,
    snippet: str,
) -> str:
    """LLM alanları veya kaynak SQL + snippet eşlemesinden satır bilgisi."""
    for key in ("line_reference", "lineReference"):
        v = item.get(key)
        if isinstance(v, str) and v.strip():
            return _normalize_line_ref_display(v)[:500]
    raw_ln = item.get("line_numbers")
    if isinstance(raw_ln, list):
        nums: list[int] = []
        for x in raw_ln:
            if isinstance(x, int) and x > 0:
                nums.append(x)
            elif isinstance(x, str) and x.strip().isdigit():
                nums.append(int(x.strip()))
        if nums:
            return _format_line_range(nums)
    ln = item.get("line_number")
    if ln is not None:
        try:
            n = int(ln)
            if n > 0:
                return f"Satır {n}"
        except (TypeError, ValueError):
            pass
    if source_sql and snippet.strip():
        inferred = _infer_line_reference_from_snippet(source_sql, snippet)
        if inferred:
            return inferred
    return ""


def _metadata_block_for_rule(
    line: RuleLine,
    metadata_context: str | None,
) -> str:
    """requires_metadata ise katalog özetini veya kullanılamadı notunu döndürür; değilse boş."""
    if not line.requires_metadata:
        return ""
    if metadata_context is None:
        return (
            "KATALOG METADATASI:\n"
            "Bu kural için şema doğrulaması amaçlanmıştır; yapıştırılan SQL veya bağlantı olmadığı için "
            "sys.dm_sql_referenced_entities / sys.columns özeti eklenemedi. Yalnızca SQL metnine güven.\n\n"
        )
    s = metadata_context.strip()
    if not s:
        return (
            "KATALOG METADATASI:\n"
            "Bağımlılık veya kolon özeti alınamadı (nesne çözülemedi veya bağımlı tablo/view yok).\n\n"
        )
    return (
        "KATALOG METADATASI (bağımlı nesneler — sunucu katalog özeti):\n"
        f"{s}\n\n"
    )





def _strip_code_fences(text: str) -> str:

    t = text.strip()

    if t.startswith("```"):

        lines = t.split("\n")

        if lines and lines[0].startswith("```"):

            lines = lines[1:]

        if lines and lines[-1].strip() == "```":

            lines = lines[:-1]

        t = "\n".join(lines).strip()

    return t





def parse_violations_json(raw: str) -> tuple[list[ViolationItem], str | None]:

    """Eski biçim: yalnızca ihlaller dizisi."""

    text = _strip_code_fences(raw)

    if not text:

        return [], "Model yanıtında JSON dizi bulunamadı."

    try:

        data = _loads_llm_json_first(text)

    except json.JSONDecodeError as e:

        return [], f"Geçersiz JSON: {e}"



    if not isinstance(data, list):

        return [], "Çözülen JSON bir dizi değil."



    out: list[ViolationItem] = []

    for item in data:

        if not isinstance(item, dict):

            continue

        sev = str(item.get("severity", "LOW")).upper()

        if sev not in ("LOW", "MEDIUM", "HIGH"):

            sev = "LOW"

        out.append(

            ViolationItem(

                rule_id=str(item.get("rule_id", "")),

                severity=sev,

                description=str(item.get("description", "")),

                line_reference=str(item.get("line_reference", "")),

                code_snippet=str(item.get("code_snippet", "")),

            )

        )

    return out, None





def _merge_rule_results(

    arr: list,

    bundle: RuleBundle,

) -> tuple[list[RuleCheckItem], list[ViolationItem], str | None]:

    by_id: dict[str, dict] = {}

    for item in arr:

        if not isinstance(item, dict):

            continue

        rid_raw = item.get("rule_id")

        if rid_raw is None:

            rid_raw = item.get("ruleId")

        if rid_raw is None:

            continue

        rid = str(rid_raw).strip()

        if rid:

            by_id[rid] = item



    warns: list[str] = []

    rule_checks: list[RuleCheckItem] = []

    violations: list[ViolationItem] = []



    for rid, tier in iter_rule_ids_ordered(bundle):

        item = by_id.get(rid)

        if item is None:

            rule_checks.append(

                RuleCheckItem(

                    rule_id=rid,

                    tier=tier,

                    status="UNKNOWN",

                    description="Model yanıtında bu kural için sonuç yok.",

                )

            )

            continue



        st = str(item.get("status", "")).upper().strip()

        st = st.replace(" ", "_").replace("-", "_")

        if st not in ("PASS", "FAIL", "NOT_APPLICABLE"):

            st = "UNKNOWN"

            warns.append(f"{rid}: geçersiz status")



        sev_raw = item.get("severity")

        sev = ""

        if st == "FAIL":

            if sev_raw is not None and str(sev_raw).strip():

                sev = str(sev_raw).upper().strip()

                if sev not in ("LOW", "MEDIUM", "HIGH"):

                    sev = "LOW"

                    warns.append(f"{rid}: geçersiz severity")

            else:

                sev = "LOW"

        else:

            if sev_raw is not None and str(sev_raw).strip():

                warns.append(f"{rid}: PASS/NOT_APPLICABLE için severity yok sayıldı")



        db_raw = item.get("decision_basis") or item.get("decisionBasis")

        db = str(db_raw or "").strip().lower().replace("-", "_")

        if db and db not in ("direct_evidence", "absence_of_evidence", "not_applicable"):

            warns.append(f"{rid}: geçersiz decision_basis")

            db = ""

        # İhlal yokken etiket göstermemek: eski model çıktılarında absence_of_evidence boşaltılır

        if db == "absence_of_evidence" and st in ("PASS", "NOT_APPLICABLE"):

            db = ""



        desc = str(item.get("description", "") or "")

        lr = str(item.get("line_reference", "") or "")

        cs = str(item.get("code_snippet", "") or "")



        rule_checks.append(

            RuleCheckItem(

                rule_id=rid,

                tier=tier,

                status=st,

                severity=sev,

                decision_basis=db,

                description=desc,

                line_reference=lr,

                code_snippet=cs,

            )

        )

        if st == "FAIL":

            violations.append(

                ViolationItem(

                    rule_id=rid,

                    severity=sev or "LOW",

                    description=desc or "(açıklama yok)",

                    line_reference=lr,

                    code_snippet=cs,

                )

            )



    expected = {rid for rid, _ in iter_rule_ids_ordered(bundle)}

    extra = set(by_id.keys()) - expected

    if extra:

        warns.append(f"Yanıtta fazladan rule_id (yok sayıldı): {sorted(extra)}")



    warn_out = "; ".join(warns) if warns else None

    return rule_checks, violations, warn_out


def _violation_entry_applies_to_rule(
    item: dict,
    rid: str,
    rule_count: int,
    warns: list[str],
) -> bool:
    """rule_code boşsa yalnızca tek kurallı isteklerde bu kurala uygulanır."""
    rc = str(item.get("rule_code") or item.get("rule_id") or "").strip()
    if not rc:
        if rule_count == 1:
            return True
        warns.append("violations içinde rule_code boş; çoklu kural bağlamında yok sayıldı")
        return False
    return rc == rid


def _looks_like_spurious_non_violation_entry(reason: str, snippet: str) -> bool:
    """LLM bazen ihlal olmayan durumu violations içinde reason/snippet ile yazar; bunları reddet."""
    text = f"{reason}\n{snippet}".strip()
    if not text:
        return False
    t = text.lower()
    if "ihlal değil" in t or "ihlal değildir" in t:
        return True
    if "dolayısıyla" in t and "ihlal" in t and ("değil" in t or "değildir" in t):
        return True
    if "ihlal sayılmaz" in t or "ihlal oluşturmaz" in t or "ihlal olarak değerlendirilmez" in t:
        return True
    if "kapsam dışı" in t and ("değil" in t or "uygulanmaz" in t or "sayılmaz" in t):
        return True
    if "bu nedenle ihlal değil" in t or "bu yüzden ihlal değil" in t:
        return True
    return False


def _merge_violations_format(
    violations_arr: list,
    bundle: RuleBundle,
    source_sql: str | None = None,
) -> tuple[list[RuleCheckItem], list[ViolationItem], str | None]:
    """LLM çıktısı { \"violations\": [ { rule_code, object_name, snippet, reason, line_reference? } ] } — uygulama modellerine dönüştürür."""
    warns: list[str] = []
    if not isinstance(violations_arr, list):
        return [], [], "violations bir dizi değil."

    normalized: list[dict] = []
    for i, item in enumerate(violations_arr):
        if isinstance(item, dict):
            normalized.append(item)
        else:
            warns.append(f"violations[{i}] nesne değil")

    ordered = list(iter_rule_ids_ordered(bundle))
    rule_count = len(ordered)
    expected_ids = {rid for rid, _ in ordered}

    rule_checks: list[RuleCheckItem] = []
    violations_out: list[ViolationItem] = []

    for rid, tier in ordered:
        sev = "HIGH" if tier == "critical" else "LOW"
        relevant = [
            x
            for x in normalized
            if _violation_entry_applies_to_rule(x, rid, rule_count, warns)
        ]

        relevant_use = [
            x
            for x in relevant
            if not _looks_like_spurious_non_violation_entry(
                str(x.get("reason") or ""),
                str(x.get("snippet") or ""),
            )
        ]

        if not relevant_use:
            rule_checks.append(
                RuleCheckItem(
                    rule_id=rid,
                    tier=tier,
                    status="PASS",
                    severity="",
                    decision_basis="",
                    description="İhlal bulunmadı.",
                    line_reference="",
                    code_snippet="",
                )
            )
            continue

        first = relevant_use[0]
        for item in relevant_use:
            oname = str(item.get("object_name") or "").strip()
            reason = str(item.get("reason") or "").strip()
            snippet = str(item.get("snippet") or "")
            lr = _line_ref_from_violation_item(item, source_sql, snippet)
            if oname and reason:
                desc = f"{oname}: {reason}"
            elif oname:
                desc = oname
            elif reason:
                desc = reason
            else:
                desc = "(ihlal)"
            violations_out.append(
                ViolationItem(
                    rule_id=rid,
                    severity=sev,
                    description=desc[:4000],
                    line_reference=lr,
                    code_snippet=snippet[:4000],
                )
            )

        r0_reason = str(first.get("reason") or "").strip()
        r0_snip = str(first.get("snippet") or "")
        lr0 = _line_ref_from_violation_item(first, source_sql, r0_snip)
        rule_checks.append(
            RuleCheckItem(
                rule_id=rid,
                tier=tier,
                status="FAIL",
                severity=sev,
                decision_basis="direct_evidence",
                description=(r0_reason or "İhlal tespit edildi.")[:500],
                line_reference=lr0,
                code_snippet=r0_snip[:500],
            )
        )

    seen_codes = set()
    for item in normalized:
        rc = str(item.get("rule_code") or item.get("rule_id") or "").strip()
        if rc:
            seen_codes.add(rc)
    extra = seen_codes - expected_ids
    if extra:
        warns.append(f"Bilinmeyen rule_code (yok sayıldı): {sorted(extra)}")

    warn_out = "; ".join(warns) if warns else None
    return rule_checks, violations_out, warn_out


def _looks_like_rule_result_entry(d: object) -> bool:
    """Model çıktısındaki tek bir kural satırı mı?"""
    if not isinstance(d, dict):
        return False
    rid = d.get("rule_id")
    if rid is None:
        rid = d.get("ruleId")
    return rid is not None and str(rid).strip() != ""


def _looks_like_violations_contract_entry(d: object) -> bool:
    """Kök dizideki öğe, {violations:[...]} sözleşmesindeki ihlal satırı gibi mi (rule_code; status yok)?"""
    if not isinstance(d, dict):
        return False
    if str(d.get("status", "")).strip():
        return False
    rc = str(d.get("rule_code") or "").strip()
    return bool(rc)


def _coerce_json_list(val: object) -> list | None:
    """Liste veya JSON dizisi metni (string) ise listeye çevirir."""
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        s = val.strip()
        if not s.startswith("["):
            return None
        try:
            parsed = _loads_llm_json_first(s)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, list) else None
    return None


def _extract_rule_results_list(data: dict) -> list | None:
    """Farklı anahtar adları ve iç içe yapılardan kural sonuçları dizisini bulur."""
    direct_keys = (
        "rule_results",
        "rule_checks",
        "results",
        "rules",
        "checks",
        "ruleResults",
        "review_results",
        "RuleResults",
    )
    for key in direct_keys:
        arr = _coerce_json_list(data.get(key))
        if arr is not None:
            return arr

    for nest_key in ("data", "response", "output", "result", "payload", "message"):
        nested = data.get(nest_key)
        if isinstance(nested, dict):
            inner = _extract_rule_results_list(nested)
            if inner is not None:
                return inner

    for v in data.values():
        arr = _coerce_json_list(v)
        if not isinstance(arr, list) or not arr:
            continue
        if not all(isinstance(x, dict) for x in arr):
            continue
        if any(_looks_like_rule_result_entry(x) for x in arr):
            return arr

    return None


def parse_review_response(

    raw: str,

    bundle: RuleBundle,

    source_sql: str | None = None,

) -> tuple[list[RuleCheckItem], list[ViolationItem], str | None]:

    text = _strip_code_fences(raw)



    data: object | None = _try_loads_llm_json_first(text)



    if isinstance(data, list) and all(isinstance(x, dict) for x in data):

        if not data:

            return _merge_violations_format([], bundle, source_sql)

        if any(_looks_like_rule_result_entry(x) for x in data):

            return _merge_rule_results(data, bundle)

        if any(_looks_like_violations_contract_entry(x) for x in data):

            return _merge_violations_format(data, bundle, source_sql)

    if isinstance(data, dict):

        viol_raw = data.get("violations")
        viol_list = _coerce_violations_list_value(viol_raw)
        if viol_list is not None:

            return _merge_violations_format(viol_list, bundle, source_sql)

        arr = _extract_rule_results_list(data)

        if isinstance(arr, list):

            return _merge_rule_results(arr, bundle)

        return (

            [],

            [],

            "JSON içinde violations veya rule_results bekleniyor.",

        )



    if text.startswith("[") or re.search(r"\[[\s\S]*\]", text):
        # Eski biçim: kök JSON dizi. Bunu kural bazlı sonuçlara dönüştürüp UI'da parse_warning
        # yerine ilgili kuralın durumunu üret.
        violations, warn = parse_violations_json(raw)

        ordered = list(iter_rule_ids_ordered(bundle))
        rid, tier = ordered[0] if ordered else ("", "normal")
        sev = "HIGH" if tier == "critical" else "LOW"

        if warn and not violations:
            # JSON hiç çözülemediyse: UNKNOWN, ama parse_warning döndürme (UI'da toplu uyarı olmasın).
            rc = RuleCheckItem(
                rule_id=rid,
                tier=tier,
                status="UNKNOWN",
                description=warn[:2000],
            )
            return [rc], [], None

        if violations:
            first = violations[0]
            rc = RuleCheckItem(
                rule_id=rid,
                tier=tier,
                status="FAIL",
                severity=first.severity or sev,
                decision_basis="direct_evidence",
                description=(first.description or "İhlal tespit edildi.")[:500],
                line_reference=first.line_reference,
                code_snippet=(first.code_snippet or "")[:500],
            )
            return [rc], violations, None

        rc = RuleCheckItem(
            rule_id=rid,
            tier=tier,
            status="PASS",
            severity="",
            decision_basis="",
            description="İhlal bulunmadı.",
            line_reference="",
            code_snippet="",
        )
        return [rc], [], None



    return [], [], "Model yanıtı JSON olarak çözülemedi."





def _normalize_openai_chat_url(url: str) -> str:
    """LM Studio: POST /v1 yerine /v1/chat/completions gerekir; kullanıcı sadece .../v1 yazabiliyor."""
    u = url.strip().rstrip("/")
    if not u:
        return u
    if u.endswith("/chat/completions"):
        return u
    if u.endswith("/v1"):
        return f"{u}/chat/completions"
    return u


def _resolved_llm_chat_api(settings) -> str:
    """openai | api_v1_chat (LM Studio vb.: POST /api/v1/chat, system_prompt + input)."""
    v = (getattr(settings, "llm_chat_api", "") or "openai").strip().lower()
    if v in ("api_v1_chat", "gpt_oss", "v1_chat"):
        return "api_v1_chat"
    return "openai"


def _llm_server_origin(base_url: str) -> str:
    """.../v1 ile bitiyorsa kök sunucu kökünü döndür (api_v1_chat için /api/v1/chat birleştirir)."""
    u = base_url.strip().rstrip("/")
    if u.endswith("/v1"):
        return u[:-3]
    return u


def _llm_chat_url_openai(settings) -> str:
    if settings.llm_chat_url.strip():
        return _normalize_openai_chat_url(settings.llm_chat_url)
    return _normalize_openai_chat_url(
        f"{settings.llm_base_url.rstrip('/')}/chat/completions"
    )


def _llm_chat_url_api_v1(settings) -> str:
    if settings.llm_chat_url.strip():
        return settings.llm_chat_url.strip().rstrip("/")
    return f"{_llm_server_origin(settings.llm_base_url)}/api/v1/chat"


def _llm_chat_url(settings) -> str:
    if _resolved_llm_chat_api(settings) == "api_v1_chat":
        out = _llm_chat_url_api_v1(settings)
    else:
        out = _llm_chat_url_openai(settings)
    _enforce_llm_network_policy(settings, out)
    return out


def _openapi_style_error_message(body: object) -> str | None:
    """LM Studio bazen 200 döner ve {'error': '...'} yazar (yanlış uç nokta vb.)."""
    if not isinstance(body, dict):
        return None
    err = body.get("error")
    if err is None:
        return None
    if isinstance(err, str):
        s = err.strip()
        return s if s else None
    if isinstance(err, dict):
        for key in ("message", "detail", "msg"):
            v = err.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return str(err).strip() or None


def _llm_connect_error_hint(
    exc: Exception,
    *,
    settings=None,
    request_url: str = "",
) -> str:
    """Bağlantı hatalarında ortam ve hedef URL'ye göre kısa ipucu (loglarda proxy yoksa yanıltıcı olmayan metin)."""
    msg = str(exc).strip() or exc.__class__.__name__
    if not (isinstance(exc, httpx.ConnectError) or "All connection attempts failed" in msg):
        return msg

    url = (request_url or "").strip()
    if settings is not None and not url:
        url = _llm_chat_url(settings)

    if isinstance(exc, (httpx.ReadTimeout, httpx.ConnectTimeout, TimeoutError)) or (
        "ReadTimeout" in msg or "timed out" in msg.lower()
    ):
        return (
            f"LLM isteği zaman aşımına uğradı (hedef: {url}). "
            "LM Studio çalışıyor mu, model yüklü mü, ağ gecikmesi veya güvenlik duvarı engeli var mı kontrol edin."
        )

    proxy_any = bool(
        os.environ.get("HTTP_PROXY")
        or os.environ.get("http_proxy")
        or os.environ.get("HTTPS_PROXY")
        or os.environ.get("https_proxy")
        or os.environ.get("ALL_PROXY")
        or os.environ.get("all_proxy")
    )

    if not proxy_any:
        return (
            f"{msg} — TCP bağlantısı kurulamadı (hedef: {url}). "
            "Yerel LLM (LM Studio, Ollama vb.) çalışıyor mu ve bu adres/port doğru mu kontrol edin; "
            "gerekirse backend/.env içinde LLM_BASE_URL veya LLM_CHAT_URL güncelleyin. "
            "LLM başka makinedeyse güvenlik duvarı ve sunucunun uygun arayüzde dinlemesi gerekir."
        )

    trust = bool(getattr(settings, "llm_http_trust_env", False)) if settings is not None else False
    return (
        f"{msg} — Hedef: {url}. HTTP(S)_PROXY ortam değişkeni tanımlı; istekler proxy üzerinden gidebilir. "
        "Doğrudan LLM’e gitmek için NO_PROXY’de LLM host’unu ekleyin veya backend/.env içinde LLM_HTTP_TRUST_ENV ile "
        f"proxy kullanımını yönetin (şu an trust_env={trust}). Uzaktan LLM için güvenlik duvarı ve dinleme adresi (0.0.0.0) kontrol edin."
    )


def _is_llm_connection_error_msg(msg: str) -> bool:
    """Kullanıcı arayüzünde tekrarlayan uzun ipuçlarını kısaltmak için."""
    if not (msg or "").strip():
        return False
    return (
        "All connection attempts failed" in msg
        or "TCP bağlantısı kurulamadı" in msg
        or "ConnectError" in msg
    )


def _brief_llm_error_for_ui(msg: str) -> str:
    """Kural kartı / özet: bağlantı hatası için kısa metin (tam ipucu yalnızca sunucu logunda)."""
    if not _is_llm_connection_error_msg(msg):
        return msg
    m = re.search(r"hedef:\s*(\S+)", msg)
    target = m.group(1).rstrip(").,;") if m else ""
    if target:
        return (
            f"LLM bağlantı hatası ({target}). "
            "LM Studio çalışıyor mu, backend/.env içinde LLM_CHAT_URL doğru mu kontrol edin; "
            "LLM_HTTP_TRUST_ENV=false (LAN IP), güvenlik duvarı ve LM Studio’nun 0.0.0.0 üzerinde dinlemesi."
        )
    return (
        "LLM bağlantı hatası (ağ / adres). backend/.env (LLM_BASE_URL, LLM_CHAT_URL) ve LM Studio sunucu ayarlarını kontrol edin."
    )


def _is_retryable_llm_transport_error(err_msg: str | None) -> bool:
    """Yalnızca ağ/okuma zaman aşımı — HTTP 500 vb. için beklemeli yeniden deneme
    toplam süreyi şişirir; eşzamanlılık `SQL_REVIEW_MAX_CONCURRENT_RULES` ile ayarlanır."""
    if not (err_msg or "").strip():
        return False
    u = err_msg.lower()
    return (
        "readtimeout" in u
        or "connecttimeout" in u
        or "timed out" in u
        or "zaman aşım" in u  # _llm_connect_error_hint (ReadTimeout)
    )


def _join_message_parts(parts: list) -> str | None:
    """LM Studio / Qwen vb.: output: [ { type, content }, ... ]"""
    msg_chunks: list[str] = []
    other_chunks: list[str] = []

    def _take_from_part(dst: list[str], part: dict) -> None:
        for k in ("content", "text"):
            c = part.get(k)
            if isinstance(c, str) and c.strip():
                dst.append(c)
                return

    for part_any in parts:
        if not isinstance(part_any, dict):
            continue
        t = str(part_any.get("type") or "").strip().lower()
        if t == "message":
            _take_from_part(msg_chunks, part_any)
        else:
            _take_from_part(other_chunks, part_any)

    chunks = msg_chunks or other_chunks
    if not chunks:
        return None
    return "\n".join(chunks).strip()


def _extract_response_text(data: object) -> str:

    """Sunucu yaniti farkli JSON sekillerinde olabilir."""

    if isinstance(data, str):

        return data

    if not isinstance(data, dict):

        return str(data)

    choices = data.get("choices")

    if isinstance(choices, list) and choices:

        first = choices[0]

        if isinstance(first, dict):

            msg = first.get("message")

            if isinstance(msg, dict) and msg.get("content"):

                return str(msg["content"]).strip()

            if first.get("text"):

                return str(first["text"]).strip()

    # LM Studio / Qwen3: { "output": [ { "type": "message", "content": "..." } ], ... }
    for key in ("output", "outputs", "messages"):
        parts = data.get(key)
        if isinstance(parts, list) and parts:
            joined = _join_message_parts(parts)
            if joined:
                return joined

    for key in ("message", "response", "output", "text", "content", "reply"):

        v = data.get(key)

        if isinstance(v, str) and v.strip():

            return v.strip()

        if isinstance(v, dict) and v.get("content"):

            return str(v["content"]).strip()

    nested = data.get("data")

    if isinstance(nested, dict):

        return _extract_response_text(nested)

    return json.dumps(data, ensure_ascii=False)


def _extract_delta_content_from_stream_chunk(obj: dict) -> str:
    """OpenAI uyumlu chat stream: choices[0].delta.content (string veya parça listesi)."""
    choices = obj.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    ch0 = choices[0]
    if not isinstance(ch0, dict):
        return ""
    delta = ch0.get("delta") or {}
    if isinstance(delta, dict):
        c = delta.get("content")
        if isinstance(c, str):
            return c
        if isinstance(c, list):
            parts: list[str] = []
            for item in c:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif isinstance(item, str):
                    parts.append(item)
            return "".join(parts)
    # Bazı sunucular (LM Studio / varyantlar) stream'de delta yerine message.content gönderir.
    msg = ch0.get("message")
    if isinstance(msg, dict) and isinstance(msg.get("content"), str):
        return msg["content"]
    return ""


def _extract_completion_tokens_from_stream_chunk(obj: dict) -> int | None:
    u = obj.get("usage")
    if isinstance(u, dict):
        ct = u.get("completion_tokens")
        if isinstance(ct, int):
            return ct
    return None


def _usage_meta_from_log_body(log_body: Any, raw_text: str) -> dict[str, Any]:
    """Tamamlanan çağrı için UI / rule_done olayına gidecek token ve karakter özeti."""
    ct: int | None = None
    if isinstance(log_body, dict):
        u = log_body.get("usage")
        if isinstance(u, dict) and isinstance(u.get("completion_tokens"), int):
            ct = u["completion_tokens"]
    return {"completion_tokens": ct, "total_chars": len(raw_text)}


async def _llm_chat_completion_api_v1(
    *,
    client: httpx.AsyncClient,
    settings,
    user_content: str,
    object_label: str,
    rule_id: str | None,
    progress: Any | None = None,
) -> tuple[str | None, str | None, dict[str, Any] | None]:
    """POST /api/v1/chat — gövde: model, system_prompt, input (OpenAI messages[] değil)."""
    url = _llm_chat_url(settings)
    payload = {
        "model": resolved_llm_model(settings),
        "system_prompt": SYSTEM_PROMPT,
        "input": user_content,
    }
    headers = {"Content-Type": "application/json"}
    key = settings.llm_api_key.strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"

    log_id = new_log_id()
    ts = log_timestamp_iso()

    try:
        response = await client.post(url, json=payload, headers=headers)
        http_status = response.status_code
        detail = ""
        try:
            detail = response.text[:8000]
        except Exception:
            pass
        response.raise_for_status()

        try:
            body_any = response.json()
        except json.JSONDecodeError:
            append_entry(
                {
                    "id": log_id,
                    "ts": ts,
                    "object_label": object_label,
                    "rule_id": rule_id,
                    "url": url,
                    "request": payload,
                    "ok": False,
                    "error": "LLM yanıtı JSON değil",
                    "http_status": http_status,
                    "response_text_fragment": detail,
                }
            )
            return None, "LLM yanıtı JSON olarak çözülemedi.", None

        if not isinstance(body_any, dict):
            append_entry(
                {
                    "id": log_id,
                    "ts": ts,
                    "object_label": object_label,
                    "rule_id": rule_id,
                    "url": url,
                    "request": payload,
                    "ok": False,
                    "error": "LLM yanıtı nesne değil",
                    "http_status": http_status,
                    "response_text_fragment": str(body_any)[:8000],
                }
            )
            return None, "LLM yanıtı beklenen formatta değil.", None

        body = body_any
        openapi_err = _openapi_style_error_message(body)
        if openapi_err:
            logger.warning(
                "LLM yanıtında error alanı (HTTP %s): %s",
                http_status,
                openapi_err[:500],
            )
            append_entry(
                {
                    "id": log_id,
                    "ts": ts,
                    "object_label": object_label,
                    "rule_id": rule_id,
                    "url": url,
                    "request": payload,
                    "ok": False,
                    "error": openapi_err,
                    "http_status": http_status,
                    "response_text_fragment": str(body)[:8000],
                }
            )
            return None, openapi_err, None

        raw_text = _extract_response_text(body).strip()
        if not raw_text:
            append_entry(
                {
                    "id": log_id,
                    "ts": ts,
                    "object_label": object_label,
                    "rule_id": rule_id,
                    "url": url,
                    "request": payload,
                    "ok": False,
                    "error": "LLM yanıtı boş veya metin çıkarılamadı",
                    "http_status": http_status,
                    "response_text_fragment": str(body)[:8000],
                }
            )
            return None, "LLM yanıtı boş veya çözümlenemedi.", None

        if progress is not None:
            ut_json: int | None = None
            u = body.get("usage")
            if isinstance(u, dict) and isinstance(u.get("completion_tokens"), int):
                ut_json = u["completion_tokens"]
            await progress(
                {
                    "phase": "llm_stream",
                    "rule_id": rule_id,
                    "completion_tokens": ut_json,
                    "total_chars": len(raw_text),
                }
            )

        append_entry(
            {
                "id": log_id,
                "ts": ts,
                "object_label": object_label,
                "rule_id": rule_id,
                "url": url,
                "request": payload,
                "ok": True,
                "response_http_status": http_status,
                "response_body": body,
                "response_text": raw_text,
            }
        )
        return raw_text, None, _usage_meta_from_log_body(body, raw_text)
    except httpx.HTTPStatusError as e:
        detail = ""
        try:
            detail = e.response.text[:8000]
        except Exception:
            pass
        logger.exception("LLM HTTP error")
        append_entry(
            {
                "id": log_id,
                "ts": ts,
                "object_label": object_label,
                "rule_id": rule_id,
                "url": url,
                "request": payload,
                "ok": False,
                "error": f"HTTP {e.response.status_code}: {detail or str(e)}",
                "http_status": e.response.status_code,
                "response_text_fragment": detail,
            }
        )
        return None, f"HTTP {e.response.status_code}: {detail or str(e)}", None
    except Exception as e:
        logger.exception("LLM request failed")
        err_msg = _llm_connect_error_hint(e, settings=settings, request_url=url)
        append_entry(
            {
                "id": log_id,
                "ts": ts,
                "object_label": object_label,
                "rule_id": rule_id,
                "url": url,
                "request": payload,
                "ok": False,
                "error": err_msg,
            }
        )
        return None, err_msg, None


async def _llm_chat_completion(
    *,
    client: httpx.AsyncClient,
    settings,
    user_content: str,
    object_label: str,
    rule_id: str | None,
    progress: Any | None = None,
) -> tuple[str | None, str | None, dict[str, Any] | None]:
    """Başarı: (metin, None, usage_meta), hata: (None, mesaj, None)."""
    extra = int(getattr(settings, "llm_request_retries", 2) or 0)
    if extra < 0:
        extra = 0
    max_attempts = extra + 1
    last: tuple[str | None, str | None, dict[str, Any] | None] = (
        None,
        "LLM yanıtı alınamadı.",
        None,
    )
    for attempt in range(max_attempts):
        if _resolved_llm_chat_api(settings) == "api_v1_chat":
            last = await _llm_chat_completion_api_v1(
                client=client,
                settings=settings,
                user_content=user_content,
                object_label=object_label,
                rule_id=rule_id,
                progress=progress,
            )
        else:
            last = await _llm_chat_completion_openai_stream(
                client=client,
                settings=settings,
                user_content=user_content,
                object_label=object_label,
                rule_id=rule_id,
                progress=progress,
            )
        text, err, _meta = last
        if text is not None:
            return last
        if attempt + 1 < max_attempts and _is_retryable_llm_transport_error(err):
            logger.warning(
                "LLM yeniden deneme %s/%s: %s",
                attempt + 2,
                max_attempts,
                (err or "")[:280],
            )
            await asyncio.sleep(min(1.5 * (2**attempt), 12.0))
            continue
        return last


async def _llm_chat_completion_openai_stream(
    *,
    client: httpx.AsyncClient,
    settings,
    user_content: str,
    object_label: str,
    rule_id: str | None,
    progress: Any | None = None,
) -> tuple[str | None, str | None, dict[str, Any] | None]:
    """OpenAI uyumlu …/chat/completions + stream=True."""
    url = _llm_chat_url(settings)
    payload = {
        "model": resolved_llm_model(settings),
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "stream": True,
    }
    headers = {"Content-Type": "application/json"}
    key = settings.llm_api_key.strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"

    log_id = new_log_id()
    ts = log_timestamp_iso()

    last_emit = 0.0

    async def _emit_llm_stream(
        total_chars: int,
        completion_tokens: int | None,
        *,
        force: bool = False,
    ) -> None:
        nonlocal last_emit
        if progress is None:
            return
        now = time.monotonic()
        if not force and (now - last_emit) < 0.2:
            return
        last_emit = now
        await progress(
            {
                "phase": "llm_stream",
                "rule_id": rule_id,
                "completion_tokens": completion_tokens,
                "total_chars": total_chars,
            }
        )

    raw_text: str | None = None
    log_body: Any = None
    http_status = 200

    try:
        async with client.stream("POST", url, json=payload, headers=headers) as response:
            response.raise_for_status()
            http_status = response.status_code

            # Ağ üzerinden satır satır oku; tüm gövdeyi aread() ile beklemek
            # UI'da canlı token akışını geciktirir (LM Studio SSE).
            saw_sse = False
            accumulated: list[str] = []
            last_usage_tokens: int | None = None
            parsed_any_chunk = False
            json_lines: list[str] = []
            capture_lines: list[str] = []

            async for line in response.aiter_lines():
                if sum(len(x) for x in capture_lines) < 8000:
                    capture_lines.append(line)

                s = line.strip()
                if s.startswith("data:"):
                    saw_sse = True
                    json_lines.clear()
                    data = s[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(chunk, dict):
                        continue
                    parsed_any_chunk = True
                    delta = _extract_delta_content_from_stream_chunk(chunk)
                    if delta:
                        accumulated.append(delta)
                    ut = _extract_completion_tokens_from_stream_chunk(chunk)
                    if ut is not None:
                        last_usage_tokens = ut
                    total = sum(len(x) for x in accumulated)
                    await _emit_llm_stream(total, last_usage_tokens, force=False)
                    continue

                if saw_sse:
                    continue

                if (
                    s.startswith("event:")
                    or s.startswith("id:")
                    or s.startswith("retry:")
                    or s.startswith(":")
                    or not s
                ):
                    continue

                json_lines.append(line)

            fragment = "\n".join(capture_lines)[:8000]

            if saw_sse:
                await _emit_llm_stream(
                    sum(len(x) for x in accumulated),
                    last_usage_tokens,
                    force=True,
                )
                raw_text = "".join(accumulated).strip()
                log_body = {
                    "streamed": True,
                    "usage": {"completion_tokens": last_usage_tokens},
                    "aggregated_length": len(raw_text),
                }
                if not parsed_any_chunk:
                    append_entry(
                        {
                            "id": log_id,
                            "ts": ts,
                            "object_label": object_label,
                            "rule_id": rule_id,
                            "url": url,
                            "request": payload,
                            "ok": False,
                            "error": "LLM SSE yanıtı çözümlenemedi veya boş",
                            "http_status": http_status,
                            "response_text_fragment": fragment,
                        }
                    )
                    return None, "LLM yanıtı çözümlenemedi.", None
            else:
                full_text = "\n".join(json_lines)
                stripped = full_text.strip()
                if not stripped:
                    append_entry(
                        {
                            "id": log_id,
                            "ts": ts,
                            "object_label": object_label,
                            "rule_id": rule_id,
                            "url": url,
                            "request": payload,
                            "ok": False,
                            "error": "LLM yanıtı boş",
                            "http_status": http_status,
                            "response_text_fragment": fragment,
                        }
                    )
                    return None, "LLM yanıtı çözümlenemedi.", None

                body: dict | None = None
                try:
                    parsed = json.loads(full_text)
                    body = parsed if isinstance(parsed, dict) else None
                except json.JSONDecodeError:
                    body = None

                if body is None:
                    for ln in full_text.splitlines():
                        ln = ln.strip()
                        if not ln.startswith("data:"):
                            continue
                        saw_sse = True
                        break
                    if saw_sse:
                        accumulated.clear()
                        last_usage_tokens = None
                        parsed_any_chunk = False
                        for ln in full_text.splitlines():
                            s2 = ln.strip()
                            if not s2.startswith("data:"):
                                continue
                            data = s2[5:].strip()
                            if data == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data)
                            except json.JSONDecodeError:
                                continue
                            if not isinstance(chunk, dict):
                                continue
                            parsed_any_chunk = True
                            delta = _extract_delta_content_from_stream_chunk(chunk)
                            if delta:
                                accumulated.append(delta)
                            ut = _extract_completion_tokens_from_stream_chunk(chunk)
                            if ut is not None:
                                last_usage_tokens = ut
                            total = sum(len(x) for x in accumulated)
                            await _emit_llm_stream(total, last_usage_tokens, force=False)
                        await _emit_llm_stream(
                            sum(len(x) for x in accumulated),
                            last_usage_tokens,
                            force=True,
                        )
                        raw_text = "".join(accumulated).strip()
                        log_body = {
                            "streamed": True,
                            "usage": {"completion_tokens": last_usage_tokens},
                            "aggregated_length": len(raw_text),
                        }
                        if not parsed_any_chunk:
                            append_entry(
                                {
                                    "id": log_id,
                                    "ts": ts,
                                    "object_label": object_label,
                                    "rule_id": rule_id,
                                    "url": url,
                                    "request": payload,
                                    "ok": False,
                                    "error": "LLM SSE yanıtı çözümlenemedi veya boş",
                                    "http_status": http_status,
                                    "response_text_fragment": fragment,
                                }
                            )
                            return None, "LLM yanıtı çözümlenemedi.", None
                    else:
                        append_entry(
                            {
                                "id": log_id,
                                "ts": ts,
                                "object_label": object_label,
                                "rule_id": rule_id,
                                "url": url,
                                "request": payload,
                                "ok": False,
                                "error": "LLM yanıtı JSON değil (stream dışı)",
                                "http_status": http_status,
                                "response_text_fragment": fragment,
                            }
                        )
                        return None, "LLM yanıtı çözümlenemedi.", None
                else:
                    openapi_err = _openapi_style_error_message(body)
                    if openapi_err:
                        logger.warning(
                            "LLM yanıtında error alanı (HTTP %s): %s",
                            http_status,
                            openapi_err[:500],
                        )
                        append_entry(
                            {
                                "id": log_id,
                                "ts": ts,
                                "object_label": object_label,
                                "rule_id": rule_id,
                                "url": url,
                                "request": payload,
                                "ok": False,
                                "error": openapi_err,
                                "http_status": http_status,
                                "response_text_fragment": str(body)[:8000],
                            }
                        )
                        return None, openapi_err, None
                    raw_text = _extract_response_text(body).strip()
                    log_body = body
                    if progress is not None:
                        ut_json: int | None = None
                        u = body.get("usage")
                        if isinstance(u, dict) and isinstance(
                            u.get("completion_tokens"), int
                        ):
                            ut_json = u["completion_tokens"]
                        await progress(
                            {
                                "phase": "llm_stream",
                                "rule_id": rule_id,
                                "completion_tokens": ut_json,
                                "total_chars": len(raw_text),
                            }
                        )
    except httpx.HTTPStatusError as e:
        detail = ""
        try:
            detail = e.response.text[:8000]
        except Exception:
            pass
        logger.exception("LLM HTTP error")
        append_entry(
            {
                "id": log_id,
                "ts": ts,
                "object_label": object_label,
                "rule_id": rule_id,
                "url": url,
                "request": payload,
                "ok": False,
                "error": f"HTTP {e.response.status_code}: {detail or str(e)}",
                "http_status": e.response.status_code,
                "response_text_fragment": detail,
            }
        )
        return None, f"HTTP {e.response.status_code}: {detail or str(e)}", None
    except Exception as e:
        logger.exception("LLM request failed")
        err_msg = _llm_connect_error_hint(e, settings=settings, request_url=url)
        append_entry(
            {
                "id": log_id,
                "ts": ts,
                "object_label": object_label,
                "rule_id": rule_id,
                "url": url,
                "request": payload,
                "ok": False,
                "error": err_msg,
            }
        )
        return None, err_msg, None

    if raw_text is None:
        return None, "LLM yanıtı alınamadı.", None

    append_entry(
        {
            "id": log_id,
            "ts": ts,
            "object_label": object_label,
            "rule_id": rule_id,
            "url": url,
            "request": payload,
            "ok": True,
            "response_http_status": http_status,
            "response_body": log_body,
            "response_text": raw_text,
        }
    )
    return raw_text, None, _usage_meta_from_log_body(log_body, raw_text)


async def review_sql(
    sql_text: str,
    object_label: str,
    metadata_context: str | None = None,
    *,
    progress: Any | None = None,
) -> tuple[list[RuleCheckItem], list[ViolationItem], str | None]:
    """Yayınlanmış her kural için ayrı LLM çağrısı; eşzamanlılık sql_review_max_concurrent_rules ile sınırlı.

    metadata_context: Veritabanı nesne incelemesinde doldurulur (bağımlılık + kolon özeti).
    None = getirilmedi (yapıştırılan SQL). Boş string = getirildi ama sonuç yok.
    """
    settings = get_settings()
    bundle = published_bundle()
    ordered = list(iter_rule_ids_ordered(bundle))
    if not ordered:
        return [], [], None

    if progress:
        await progress(
            {
                "phase": "rules_batch_start",
                "object_label": object_label,
                "rules_total": len(ordered),
            }
        )

    sql_capped = sql_text[:120_000]
    numbered = _numbered_sql(sql_capped)

    read_sec = float(getattr(settings, "llm_read_timeout_seconds", 900.0) or 900.0)
    if read_sec < 60.0:
        read_sec = 60.0
    connect_sec = min(120.0, read_sec)

    ua = (settings.llm_http_user_agent or "").strip() or "DWHCodeReview-Backend/1.0"
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(read_sec, connect=connect_sec),
        trust_env=settings.llm_http_trust_env,
        verify=_llm_ssl_context(),
        headers={"User-Agent": ua},
        limits=httpx.Limits(
            max_connections=5000,
            max_keepalive_connections=500,
        ),
    ) as http_client:

        async def one_rule(
            rid: str, tier: str, rule_index: int
        ) -> tuple[RuleCheckItem, list[ViolationItem], str | None]:
            line = get_rule_line(bundle, rid)
            if line is None:
                return (
                    RuleCheckItem(
                        rule_id=rid,
                        tier=tier,
                        status="UNKNOWN",
                        description="Kural metni bulunamadı.",
                    ),
                    [],
                    None,
                )

            mini = _mini_bundle_for_rule(line, tier)
            meta_block = _metadata_block_for_rule(line, metadata_context)
            threshold = int(getattr(settings, "sql_review_two_part_threshold_chars", 45_000) or 45_000)
            use_two = len(sql_capped) > threshold
            p1, p2, line_start_b = _split_sql_into_two_parts(sql_capped)
            if use_two and not (p2 or "").strip():
                use_two = False

            if progress:
                await progress(
                    {
                        "phase": "rule_start",
                        "object_label": object_label,
                        "rule_id": rid,
                        "tier": tier,
                        "rule_index": rule_index,
                        "rules_total": len(ordered),
                        "sql_two_part": use_two,
                    }
                )

            if not use_two:
                user_content = USER_PROMPT_TEMPLATE_SINGLE.format(
                    rule_id=rid,
                    rule_text=line.text,
                    sql_scope_notice="",
                    metadata_block=meta_block,
                    numbered_sql=numbered,
                )
                raw, err, usage_meta = await _llm_chat_completion(
                    client=http_client,
                    settings=settings,
                    user_content=user_content,
                    object_label=object_label,
                    rule_id=rid,
                    progress=progress,
                )

                if progress:
                    rd: dict[str, Any] = {
                        "phase": "rule_done",
                        "object_label": object_label,
                        "rule_id": rid,
                        "tier": tier,
                        "rule_index": rule_index,
                        "rules_total": len(ordered),
                        "ok": err is None and bool(raw and raw.strip()),
                        "sql_two_part": False,
                    }
                    if usage_meta is not None:
                        rd["completion_tokens"] = usage_meta.get("completion_tokens")
                        rd["total_chars"] = usage_meta.get("total_chars")
                    await progress(rd)

                if err is not None or not raw:
                    err_s = err or "LLM yanıtı alınamadı."
                    desc = (
                        _brief_llm_error_for_ui(err_s)
                        if _is_llm_connection_error_msg(err_s)
                        else err_s
                    )
                    return (
                        RuleCheckItem(
                            rule_id=rid,
                            tier=tier,
                            status="UNKNOWN",
                            description=desc,
                        ),
                        [],
                        err,
                    )

                rule_checks, violations, warn = parse_review_response(
                    raw, mini, source_sql=sql_capped
                )
                if not rule_checks:
                    return (
                        RuleCheckItem(
                            rule_id=rid,
                            tier=tier,
                            status="UNKNOWN",
                            description=warn or "Çözümleme sonucu boş.",
                        ),
                        [],
                        warn,
                    )

                return rule_checks[0], violations, warn

            notice1, notice2 = _two_part_scope_notices(sql_capped, line_start_b)
            num1 = _numbered_sql(p1, start_line=1)
            num2 = _numbered_sql(p2, start_line=line_start_b)
            uc1 = USER_PROMPT_TEMPLATE_SINGLE.format(
                rule_id=rid,
                rule_text=line.text,
                sql_scope_notice=notice1,
                metadata_block=meta_block,
                numbered_sql=num1,
            )
            uc2 = USER_PROMPT_TEMPLATE_SINGLE.format(
                rule_id=rid,
                rule_text=line.text,
                sql_scope_notice=notice2,
                metadata_block=meta_block,
                numbered_sql=num2,
            )

            raw_a, err_a, meta_a = await _llm_chat_completion(
                client=http_client,
                settings=settings,
                user_content=uc1,
                object_label=object_label,
                rule_id=f"{rid}#1/2",
                progress=progress,
            )
            raw_b, err_b, meta_b = await _llm_chat_completion(
                client=http_client,
                settings=settings,
                user_content=uc2,
                object_label=object_label,
                rule_id=f"{rid}#2/2",
                progress=progress,
            )

            ok_merge = err_a is None and err_b is None and bool(
                (raw_a or "").strip() or (raw_b or "").strip()
            )
            if progress:
                rd2: dict[str, Any] = {
                    "phase": "rule_done",
                    "object_label": object_label,
                    "rule_id": rid,
                    "tier": tier,
                    "rule_index": rule_index,
                    "rules_total": len(ordered),
                    "ok": ok_merge,
                    "sql_two_part": True,
                }
                ct_a = (meta_a or {}).get("completion_tokens")
                ct_b = (meta_b or {}).get("completion_tokens")
                if isinstance(ct_a, int) and isinstance(ct_b, int):
                    rd2["completion_tokens"] = ct_a + ct_b
                elif isinstance(ct_a, int):
                    rd2["completion_tokens"] = ct_a
                elif isinstance(ct_b, int):
                    rd2["completion_tokens"] = ct_b
                tc_a = (meta_a or {}).get("total_chars")
                tc_b = (meta_b or {}).get("total_chars")
                if isinstance(tc_a, int) and isinstance(tc_b, int):
                    rd2["total_chars"] = tc_a + tc_b
                elif isinstance(tc_a, int):
                    rd2["total_chars"] = tc_a
                elif isinstance(tc_b, int):
                    rd2["total_chars"] = tc_b
                await progress(rd2)

            rc_m, viol_m, warn_m = _merge_two_part_single_rule(
                rid,
                tier,
                err_a=err_a,
                raw_a=raw_a,
                err_b=err_b,
                raw_b=raw_b,
                mini=mini,
                source_sql=sql_capped,
            )
            if rc_m.status == "UNKNOWN" and (err_a or err_b):
                err_s = warn_m or err_a or err_b or "LLM yanıtı alınamadı."
                desc = (
                    _brief_llm_error_for_ui(err_s)
                    if _is_llm_connection_error_msg(err_s)
                    else (rc_m.description or err_s)[:2000]
                )
                return (
                    RuleCheckItem(
                        rule_id=rid,
                        tier=tier,
                        status="UNKNOWN",
                        description=desc,
                    ),
                    [],
                    warn_m or err_a or err_b,
                )
            return rc_m, viol_m, warn_m

        max_concurrent = int(
            getattr(settings, "sql_review_max_concurrent_rules", 6) or 6
        )
        if max_concurrent < 1:
            max_concurrent = 1
        sem = asyncio.Semaphore(max_concurrent)

        async def run_bounded(
            rid: str, tier: str, rule_index: int
        ) -> tuple[RuleCheckItem, list[ViolationItem], str | None]:
            async with sem:
                return await one_rule(rid, tier, rule_index)

        results = await asyncio.gather(
            *[
                run_bounded(rid, tier, i + 1)
                for i, (rid, tier) in enumerate(ordered)
            ]
        )

        rule_checks_all = [r[0] for r in results]
        violations_all: list[ViolationItem] = []
        for r in results:
            violations_all.extend(r[1])

        conn_groups: dict[str, list[str]] = {}
        other_warns: list[str] = []
        _legacy_markers = (
            "PASS/FAIL",
            "Eski çıktı biçimi",
            "Eski",
            "çıktı biçimi",
        )
        for (rid, _), r in zip(ordered, results):
            w = r[2]
            if not w:
                continue
            # Eski-format uyarısı artık kural sonuçlarına mapleniyor; UI parse_warning'ini kirletmesin.
            wl = str(w)
            if any(m in wl for m in _legacy_markers):
                continue
            if _is_llm_connection_error_msg(w):
                brief = _brief_llm_error_for_ui(w)
                conn_groups.setdefault(brief, []).append(rid)
            else:
                other_warns.append(f"[{rid}] {w}")
        warn_parts: list[str] = []
        for brief, rids in conn_groups.items():
            if len(rids) == 1:
                warn_parts.append(f"[{rids[0]}] {brief}")
            else:
                warn_parts.append(f"[{', '.join(rids)}] {brief}")
        warn_parts.extend(other_warns)
        parse_warning = "; ".join(warn_parts) if warn_parts else None
        if parse_warning and ("PASS/FAIL" in parse_warning or "çıktı biçimi" in parse_warning):
            parse_warning = None

        return rule_checks_all, violations_all, parse_warning



