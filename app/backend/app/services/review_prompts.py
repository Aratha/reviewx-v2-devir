"""Prompts, line numbering and the two-part split (sql-review 003 Requirement 8, 9 and 6).

The system prompt, the single-rule user template, ``L001`` numbering, the half split and the
part notices are ported unchanged from the previous application's ``services/llm_review.py``.
The metadata block keeps the source notes and adds the Requirement 6 note for a failed fetch.
"""

from app.domain.review import MetadataContext, MetadataSource, ReviewRule

# Both prompts are ported byte for byte from the previous application.
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


USER_PROMPT_TEMPLATE = """Aşağıdaki SQL kodunu verilen kural tanımına göre analiz et.

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


def numbered_sql(sql: str, start_line: int = 1) -> str:
    """Prefix each line with ``L001``; the width grows past three digits when needed."""

    if not sql:
        return ""
    lines = sql.splitlines()
    last_number = start_line + len(lines) - 1
    width = max(3, len(str(last_number)))
    return "\n".join(
        f"L{number:0{width}d}  {line}" for number, line in enumerate(lines, start=start_line)
    )


def split_into_two_parts(sql: str) -> tuple[str, str, int]:
    """Halve by lines (by characters for one line); returns part 2's first line number."""

    if not sql:
        return "", "", 1
    lines = sql.splitlines()
    if len(lines) >= 2:
        middle = max(1, len(lines) // 2)
        return "\n".join(lines[:middle]), "\n".join(lines[middle:]), middle + 1
    middle = max(1, len(sql) // 2)
    return sql[:middle], sql[middle:], 1


def two_part_scope_notices(sql: str, second_part_first_line: int) -> tuple[str, str]:
    """The "apply only to this part" notes of part 1 and part 2."""

    lines = sql.splitlines()
    if len(lines) >= 2:
        total = len(lines)
        first_end = second_part_first_line - 1
        return (
            (
                f"ÖNEMLİ — PARÇA 1/2: Aşağıdaki kod yalnızca nesnenin satır 1–{first_end} "
                f"bölümüdür (toplam {total} satır). Kuralı yalnızca bu parçaya uygula; parça "
                "2’deki kodu varsayma veya birleştirerek yorumlama.\n\n"
            ),
            (
                f"ÖNEMLİ — PARÇA 2/2: Aşağıdaki kod yalnızca nesnenin satır "
                f"{second_part_first_line}–{total} bölümüdür (toplam {total} satır). Kuralı "
                "yalnızca bu parçaya uygula; parça 1’deki kodu varsayma.\n\n"
            ),
        )
    return (
        (
            "ÖNEMLİ — PARÇA 1/2: Aşağıdaki metin orijinal tek satırın (veya tek parçanın) ilk "
            "yarısıdır. Kuralı yalnızca bu metne uygula.\n\n"
        ),
        (
            "ÖNEMLİ — PARÇA 2/2: Aşağıdaki metin aynı satırın/parçanın devamıdır. Kuralı "
            "yalnızca bu metne uygula.\n\n"
        ),
    )


def metadata_block(rule: ReviewRule, metadata: MetadataContext) -> str:
    """The catalog note of a flagged rule; unflagged rules get no block at all."""

    if not rule.requires_metadata:
        return ""
    if metadata.source is MetadataSource.NOT_AVAILABLE_FOR_SCRIPT:
        return (
            "KATALOG METADATASI:\n"
            "Bu kural için şema doğrulaması amaçlanmıştır; yapıştırılan SQL veya bağlantı olmadığı "
            "için sys.dm_sql_referenced_entities / sys.columns özeti eklenemedi. Yalnızca SQL "
            "metnine güven.\n\n"
        )
    if metadata.source is MetadataSource.FAILED:
        return (
            "KATALOG METADATASI:\n"
            "Bağımlılık veya kolon özeti alınamadı; yalnızca SQL metnine güven.\n\n"
        )
    summary = metadata.text.strip()
    if not summary:
        return (
            "KATALOG METADATASI:\n"
            "Bağımlılık veya kolon özeti alınamadı (nesne çözülemedi veya bağımlı tablo/view "
            "yok).\n\n"
        )
    return f"KATALOG METADATASI (bağımlı nesneler — sunucu katalog özeti):\n{summary}\n\n"


def user_prompt(
    rule: ReviewRule, *, numbered: str, metadata: MetadataContext, scope_notice: str = ""
) -> str:
    return USER_PROMPT_TEMPLATE.format(
        rule_id=rule.code,
        rule_text=rule.text,
        sql_scope_notice=scope_notice,
        metadata_block=metadata_block(rule, metadata),
        numbered_sql=numbered,
    )
