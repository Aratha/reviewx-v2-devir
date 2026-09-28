#!/usr/bin/env python3
"""Bounded, offline preparation of the project's unmanaged root Python environment.

The only implementation of `.venv` preparation and validation. The project creation flows run it
right after the canonical files are published, and the prompt gate names its `hazirla` command as
the one recovery step. The factory package loads the same file through
``kt_scaffold.python_environment``.

Usage from the project root, on the technology profile's Python:

    python3.14 .kt-scaffold/hooks/python_environment.py hazirla
    python3.14 .kt-scaffold/hooks/python_environment.py dogrula
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
import re
import runpy
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

# A host python3 may be older than the profile; keep 3.9 syntax so a wrong interpreter can still
# report which one to use. Everything past the version check runs on the profile's Python.

_HOST_PROBE = """import json, pathlib, sys, sysconfig, venv
suffix = "t" if sysconfig.get_config_var("Py_GIL_DISABLED") else ""
suffix += "_d" if hasattr(sys, "gettotalrefcount") else ""
launcher_dir = pathlib.Path(venv.__file__).parent / "scripts" / "nt"
launcher = launcher_dir / ("venvlauncher" + suffix + ".exe")
print(json.dumps({"version": ".".join(map(str, sys.version_info[:3])),
                  "venv_launcher": str(launcher)}))
"""

# On Python 3.14 -S deliberately leaves sys.prefix at the base interpreter.
# Run the trusted stdlib's prefix discovery while disabling every site directory
# and startup hook. Existing .pth, sitecustomize, and pip code must never execute.
_ENVIRONMENT_PROBE = """import site, sys
site.addsitedir = lambda directory, known_paths=None: known_paths
site.execsitecustomize = lambda: None
site.execusercustomize = lambda: None
site.main()
import importlib.machinery, importlib.metadata, json, sysconfig
packages = sysconfig.get_path("purelib")
spec = importlib.machinery.PathFinder.find_spec("pip", [packages])
pip_metadata = any(dist.metadata.get("Name", "").lower() == "pip"
                   for dist in importlib.metadata.distributions(path=[packages]))
print(json.dumps({"version": ".".join(map(str, sys.version_info[:3])),
                  "prefix": sys.prefix, "base_prefix": sys.base_prefix,
                  "packages": packages,
                  "pip_available": bool(spec and spec.origin and pip_metadata)}))
"""


# The command's printed result crosses into the client and the MCP receipt. Only these fields,
# each with a fixed meaning and no local path or probe content, may leave the process.
PUBLIC_RESULT_FIELDS = (
    "status",
    "path",
    "required_version",
    "observed_version",
    "isolated",
    "prefix_matches_target",
    "system_site_packages",
    "pip_available",
    "pip_check",
    "error",
)
_VERSION = re.compile(r"(\d{1,2})\.(\d{1,3})\.(\d{1,4})")


class _EnvironmentError(ValueError):
    """A bounded local preparation failure, safe to include in the local result."""


@functools.lru_cache(maxsize=1)
def _records() -> dict[str, Any]:
    # The profile reader and the repair command belong to the interpreter helpers there.
    return runpy.run_path(str(Path(__file__).with_name("governance_records.py")))


def _version_text(value: object) -> str | None:
    """A probed `major.minor.micro` rebuilt from its integers; other probe output is withheld."""

    match = _VERSION.fullmatch(value) if isinstance(value, str) else None
    if match is None:
        return None
    return ".".join(str(int(part)) for part in match.groups())


def public_result(result: dict[str, object]) -> dict[str, object]:
    """The allow-listed fields of a preparation result, as the command prints them."""

    return {name: result[name] for name in PUBLIC_RESULT_FIELDS if name in result}


def repair_command(required: str) -> str:
    """The one command that prepares `.venv` from the project root on the profile's Python."""

    return str(_records()["repair_command"](required))


def required_version(root: Path) -> str | None:
    """The `major.minor` Python version fixed by the project's technology profile."""

    version: str | None = _records()["profile_python_version"](root)
    return version


def minimum_version(root: Path) -> str | None:
    """The lowest `major.minor.micro` Python the project's technology profile admits."""

    version: str | None = _records()["profile_python_minimum"](root)
    return version


def meets_minimum(version: str, minimum: str | None) -> bool:
    """Whether a probed `major.minor.micro` is at or above the profile's security floor."""

    if minimum is None:
        return True
    return tuple(int(part) for part in version.split(".")) >= tuple(
        int(part) for part in minimum.split(".")
    )


def _run_python(
    executable: Path, arguments: list[str], root: Path
) -> subprocess.CompletedProcess[str]:
    # Do not pass credentials, PYTHONPATH, pip settings, or user startup configuration.
    environment = {"PATH": os.defpath}
    for name in ("SYSTEMROOT", "WINDIR"):
        if name in os.environ:
            environment[name] = os.environ[name]
    try:
        return subprocess.run(
            [str(executable), "-I", "-S", "-B", *arguments],
            cwd=root,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
            timeout=90,
        )
    except subprocess.TimeoutExpired as exc:
        raise _EnvironmentError("Yerel Python işlemi zaman aşımına uğradı.") from exc
    except (OSError, subprocess.CalledProcessError) as exc:
        raise _EnvironmentError(
            "Yerel Python veya standart venv/ensurepip işlemi başarısız."
        ) from exc


def _probe(executable: Path, script: str, root: Path) -> dict[str, Any]:
    result = _run_python(executable, ["-c", script], root)
    try:
        observed: object = json.loads(result.stdout)
    except (ValueError, TypeError) as exc:
        raise _EnvironmentError("Yerel Python doğrulama çıktısı geçersiz.") from exc
    if not isinstance(observed, dict):
        raise _EnvironmentError("Yerel Python doğrulama çıktısı geçersiz.")
    return observed


def _trusted_python(root: Path) -> tuple[Path, dict[str, Any]]:
    # The running interpreter is the trusted one; never search a target-controlled PATH.
    executable_name = getattr(sys, "_base_executable", None) or sys.executable
    if not isinstance(executable_name, str) or not executable_name:
        raise _EnvironmentError("Kurulu güvenilir Python yorumlayıcısı bulunamadı.")
    executable = Path(executable_name).resolve(strict=True)
    if not executable.is_file():
        raise _EnvironmentError("Kurulu güvenilir Python yorumlayıcısı bulunamadı.")
    observed = _probe(executable, _HOST_PROBE, root)
    return executable, observed


def _is_link(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def _root_directory(root: Path) -> Path:
    if _is_link(root) or not root.is_dir():
        raise _EnvironmentError("Proje kökü gerçek ve mevcut bir dizin olmalıdır.")
    return root.resolve(strict=True)


def _read_config(environment: Path, executable: Path, version: str) -> None:
    config_path = environment / "pyvenv.cfg"
    if _is_link(config_path) or not config_path.is_file() or config_path.stat().st_size > 16384:
        raise _EnvironmentError("Mevcut .venv yapılandırması eksik veya güvenli değil.")
    config: dict[str, str] = {}
    for line in config_path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if not separator or not key.strip() or key.strip() in config:
            raise _EnvironmentError("Mevcut .venv yapılandırması geçersiz.")
        config[key.strip()] = value.strip()
    if config.get("include-system-site-packages") != "false":
        raise _EnvironmentError("Mevcut .venv sistem site-packages erişimini kapatmalıdır.")
    if config.get("version") != version:
        raise _EnvironmentError(
            "Mevcut .venv Python sürümü kurulu güvenilir yorumlayıcıyla uyuşmuyor."
        )
    if not config.get("command", "").endswith(" " + str(environment)):
        raise _EnvironmentError("Mevcut .venv başka bir hedefte oluşturulmuş veya kaynağı eksik.")
    origin = config.get("executable")
    home = config.get("home")
    if (
        not origin
        or not home
        or Path(origin).resolve(strict=True) != executable
        or not Path(home).is_absolute()
    ):
        raise _EnvironmentError("Mevcut .venv yorumlayıcı kaynağı güvenilir değil.")
    home_python = Path(home) / executable.name
    if home_python.resolve(strict=True) != executable:
        raise _EnvironmentError("Mevcut .venv standart kitaplık kaynağı güvenilir değil.")


def _same_bytes(left: Path, right: Path) -> bool:
    if left.stat().st_size != right.stat().st_size:
        return False
    with left.open("rb") as left_handle, right.open("rb") as right_handle:
        return (
            hashlib.file_digest(left_handle, "sha256").digest()
            == hashlib.file_digest(right_handle, "sha256").digest()
        )


def _interpreter_path(environment: Path, platform_name: str) -> Path:
    return environment / ("Scripts/python.exe" if platform_name == "nt" else "bin/python")


def _interpreter_source(executable: Path, host: dict[str, Any], platform_name: str) -> Path:
    if platform_name != "nt":
        return executable
    launcher = host.get("venv_launcher")
    if not isinstance(launcher, str):
        raise _EnvironmentError("Güvenilir Python ortam başlatıcısı bulunamadı.")
    return Path(launcher)


def _validate_paths(environment: Path, executable: Path, host: dict[str, Any]) -> Path:
    if _is_link(environment) or not environment.is_dir():
        raise _EnvironmentError("Mevcut .venv gerçek bir dizin olmalıdır.")
    interpreter = _interpreter_path(environment, os.name)
    interpreter_directory = interpreter.parent
    if _is_link(interpreter_directory) or not interpreter_directory.is_dir():
        raise _EnvironmentError("Mevcut .venv yorumlayıcı dizini güvenli değil.")
    if not interpreter.is_file():
        raise _EnvironmentError("Mevcut .venv yorumlayıcısı eksik.")
    trusted_binary = _interpreter_source(executable, host, os.name)
    if not _same_bytes(interpreter, trusted_binary):
        raise _EnvironmentError("Mevcut .venv yorumlayıcı baytları güvenilir kaynakla uyuşmuyor.")
    for parent, directories, files in os.walk(environment, followlinks=False):
        for name in directories + files:
            path = Path(parent) / name
            if path.parent in {environment, interpreter_directory} and name.endswith("._pth"):
                raise _EnvironmentError("Mevcut .venv özel Python başlangıç yolu içeriyor.")
            if path.parent in {environment, interpreter_directory, environment / "lib"} and (
                name.lower().endswith((".dll", ".dylib", ".pyd")) or ".so" in name.lower()
            ):
                raise _EnvironmentError(
                    "Mevcut .venv yorumlayıcı yanında özel dinamik kitaplık içeriyor."
                )
            if not _is_link(path):
                continue
            resolved = path.resolve(strict=True)
            ordinary_interpreter = (
                path.parent == interpreter_directory
                # Python 3.14 venv also links the `𝜋thon` alias to the same interpreter.
                and re.fullmatch(r"python(?:\d+(?:\.\d+)?)?|𝜋thon", path.name) is not None
                and resolved == executable
            )
            ordinary_lib64 = path == environment / "lib64" and resolved == environment / "lib"
            if not ordinary_interpreter and not ordinary_lib64:
                raise _EnvironmentError("Mevcut .venv beklenmeyen sembolik bağlantı içeriyor.")
    return interpreter


def _validate(environment: Path, executable: Path, host: dict[str, Any]) -> dict[str, object]:
    if _is_link(environment) or not environment.is_dir():
        raise _EnvironmentError("Mevcut .venv gerçek bir dizin olmalıdır.")
    _read_config(environment, executable, str(host["version"]))
    interpreter = _validate_paths(environment, executable, host)
    identity = environment.stat()
    observed = _probe(interpreter, _ENVIRONMENT_PROBE, environment.parent)
    current = environment.lstat()
    if (
        _is_link(environment)
        or (identity.st_dev, identity.st_ino) != (current.st_dev, current.st_ino)
        or observed.get("version") != host["version"]
        or observed.get("prefix") != str(environment)
        or observed.get("base_prefix") == str(environment)
    ):
        raise _EnvironmentError(
            "Mevcut .venv sürüm, nihai hedef veya izolasyon doğrulamasını geçemedi."
        )
    packages = observed.get("packages")
    if not isinstance(packages, str) or not Path(packages).is_relative_to(environment):
        raise _EnvironmentError("Mevcut .venv paket yolu proje ortamının dışında.")
    if observed.get("pip_available") is not True:
        raise _EnvironmentError("Mevcut .venv içinde pip erişimi doğrulanamadı.")
    return {
        "observed_version": _version_text(observed["version"]),
        "isolated": True,
        "prefix_matches_target": True,
        "system_site_packages": False,
        "pip_available": True,
        "pip_check": "metadata-and-module-discovery-without-package-execution",
    }


def _result(*, create: bool, root: Path) -> dict[str, object]:
    result: dict[str, object] = {
        "status": "failed",
        "path": ".venv",
        "required_version": None,
        "observed_version": None,
        "isolated": False,
        "prefix_matches_target": False,
        "pip_available": False,
    }
    owned_environment: Path | None = None
    owned_identity: tuple[int, int] | None = None
    try:
        root = _root_directory(root)
        required = required_version(root)
        if required is None:
            raise _EnvironmentError("Proje teknoloji profilinde Python sürümü okunamadı.")
        result["required_version"] = required
        executable, host = _trusted_python(root)
        version = _version_text(host.get("version"))
        result["observed_version"] = version
        if version is None or not version.startswith(required + "."):
            raise _EnvironmentError(
                f"Kurulu Python sürümü {required}.x koşulunu sağlamıyor; "
                f"proje kökünde çalıştırın: {repair_command(required)}"
            )
        minimum = minimum_version(root)
        if not meets_minimum(version, minimum):
            raise _EnvironmentError(
                f"Kurulu Python {version}, projenin istediği en az Python {minimum} sürümünden "
                f"eski; güvenlik düzeltmeleri için kurumsal uygulama kataloğundan Python "
                f"{minimum} veya daha yenisini kurun."
            )
        environment = root / ".venv"
        if not environment.exists() and not _is_link(environment) and create:
            # mkdir is the ownership claim: a concurrent caller may only inspect
            # this incomplete environment, never share or overwrite its builder.
            environment.mkdir(mode=0o700)
            identity = environment.stat()
            owned_environment = environment
            owned_identity = (identity.st_dev, identity.st_ino)
            _run_python(executable, ["-m", "venv", "--copies", str(environment)], root)
        result.update(_validate(environment, executable, host))
        result["status"] = "created" if owned_environment is not None else "unchanged"
    except _EnvironmentError as exc:
        result["error"] = str(exc)
    except (OSError, ValueError, KeyError, TypeError):
        result["error"] = "Yerel Python ortamı güvenle hazırlanamadı veya doğrulanamadı."
    finally:
        if result["status"] == "failed" and owned_environment is not None:
            try:
                current = owned_environment.lstat()
                if (
                    not _is_link(owned_environment)
                    and stat.S_ISDIR(current.st_mode)
                    and (current.st_dev, current.st_ino) == owned_identity
                ):
                    shutil.rmtree(owned_environment)
            except OSError:
                # A later retry rejects remaining partial state instead of claiming
                # it or deleting an environment it does not own.
                pass
    return result


def prepare(root: Path) -> dict[str, object]:
    """Create only an absent .venv; preserve and safely inspect existing environments."""
    return _result(create=True, root=root)


def validate(root: Path) -> dict[str, object]:
    """Inspect the exact root .venv without writes or existing package execution."""
    return _result(create=False, root=root)


def main(arguments: list[str] | None = None) -> int:
    selected = sys.argv[1:] if arguments is None else arguments
    if selected not in (["hazirla"], ["dogrula"]):
        print("usage: python_environment.py hazirla|dogrula", file=sys.stderr)
        return 2
    root = Path(__file__).resolve(strict=True).parents[2]
    required = required_version(root)
    running = f"{sys.version_info.major}.{sys.version_info.minor}"
    if required is not None and running != required:
        result: dict[str, object] = {
            "status": "failed",
            "path": ".venv",
            "required_version": required,
            "observed_version": ".".join(map(str, sys.version_info[:3])),
            "error": (
                f"Bu komut Python {required} ile çalışmalıdır; "
                f"proje kökünde çalıştırın: {repair_command(required)}"
            ),
        }
    else:
        result = prepare(root) if selected == ["hazirla"] else validate(root)
    print(json.dumps(public_result(result), ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] in {"created", "unchanged"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
