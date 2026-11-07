"""Construir, inspeccionar y probar el ZIP antes de reemplazar el entregable."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent.parent
ALEXA_REQUIRED = {"lambda_function.py", "handlers/__init__.py", "services/__init__.py", "ask_sdk_core/__init__.py", "ask_sdk_model/__init__.py", "boto3/__init__.py", "botocore/__init__.py"}
ADMIN_REQUIRED = {"admin_lambda_function.py", "administration/__init__.py", "services/__init__.py", "boto3/__init__.py", "botocore/__init__.py"}
PUBLIC_CA_FILES = {"botocore/cacert.pem", "certifi/cacert.pem"}
FORBIDDEN_PARTS = {".venv", ".local", "__pycache__", "tests", "test", ".git"}
FORBIDDEN_ROOTS = {"include", "events", "scripts", "build", "dist", "lambda"}


def package_files(stage, required, flavor):
    result = []
    for path in sorted(stage.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(stage)
        if set(relative.parts) & {"__pycache__", "tests", "test"} or path.suffix == ".pyc":
            continue
        if path.is_symlink() or set(relative.parts) & FORBIDDEN_PARTS or relative.parts[0] in FORBIDDEN_ROOTS:
            raise ValueError("Unexpected package entry: " + str(relative))
        if any(part.startswith(".env") for part in relative.parts) or path.name in {"secrets.h", "config.h", "credentials", "config"}:
            raise ValueError("Forbidden configuration: " + str(relative))
        if path.suffix in {".so", ".pyd", ".dylib", ".key", ".p12", ".pfx"}:
            raise ValueError("Native binary or private certificate: " + str(relative))
        if path.suffix == ".pem" and relative.as_posix() not in PUBLIC_CA_FILES:
            raise ValueError("Unexpected PEM: " + str(relative))
        content = path.read_bytes()
        for marker in (b"-----BEGIN PRIVATE KEY-----", b"-----BEGIN RSA PRIVATE KEY-----", b"-----BEGIN EC PRIVATE KEY-----"):
            if marker in content:
                raise ValueError("Private key marker: " + str(relative))
        if path.suffix == ".py":
            compile(content, relative.as_posix(), "exec", dont_inherit=True)
        result.append((path, relative.as_posix()))
    if not required <= {name for _, name in result}:
        raise ValueError("Missing root modules or dependencies")
    names = {name for _, name in result}
    if flavor == "alexa":
        assert "admin_lambda_function.py" not in names
        assert not any(name.startswith("administration/") for name in names)
    else:
        assert "lambda_function.py" not in names
        assert not any(name.startswith(("handlers/", "ask_sdk_")) for name in names)
        assert "services/dynamodb_service.py" not in names
    for wheel in stage.glob("*.dist-info/WHEEL"):
        if "Root-Is-Purelib: true" not in wheel.read_text():
            raise ValueError("Not a universal Python wheel")
    return result


def main():
    if sys.version_info[:2] != (3, 13):
        raise SystemExit("Requires Python 3.13")
    stage = Path(sys.argv[1]).resolve()
    flavor = sys.argv[2]
    if flavor not in {"alexa", "admin"}:
        raise ValueError("Unknown flavor")
    required = ALEXA_REQUIRED if flavor == "alexa" else ADMIN_REQUIRED
    handler_module = "lambda_function" if flavor == "alexa" else "admin_lambda_function"
    requirements = "requirements.txt" if flavor == "alexa" else "requirements-admin.txt"
    report_name = "build-report.json" if flavor == "alexa" else "admin-build-report.json"
    files = package_files(stage, required, flavor)
    destination = ROOT / "dist" / ("SmartParkAlexaBackend.zip" if flavor == "alexa" else "SmartParkPairingAdmin.zip")
    # Solo publicar el ZIP local final despues de verificarlo completamente.
    with tempfile.TemporaryDirectory(prefix="validation.", dir=ROOT / "build") as directory:
        scratch = Path(directory)
        candidate = scratch / destination.name
        with zipfile.ZipFile(candidate, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path, name in files:
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, path.read_bytes())
        with zipfile.ZipFile(candidate) as archive:
            if archive.testzip() is not None:
                raise ValueError("ZIP integrity failure")
            entries = archive.namelist()
            assert required <= set(entries)
            assert not any(name.startswith("lambda/") for name in entries)
            uncompressed = sum(entry.file_size for entry in archive.infolist())
            assert candidate.stat().st_size < 50 * 1024**2
            assert uncompressed < 250 * 1024**2
            extracted = scratch / "extracted"
            archive.extractall(extracted)
        # Import y pruebas del codigo/dependencias extraidos, no los del repo/.venv.
        code = r'''
import importlib, json, os, socket, sys, unittest
from pathlib import Path
root = Path(sys.argv[1]).resolve()
sys.path[:] = [str(root)] + [p for p in sys.path if not ({"site-packages", "dist-packages"} & set(Path(p).parts))]
def no_network(*args, **kwargs):
    raise AssertionError("Network forbidden during package validation")
socket.create_connection = no_network
socket.socket.connect = no_network
os.environ["AWS_EC2_METADATA_DISABLED"] = "true"
flavor = sys.argv[3]
handler_name = "lambda_function" if flavor == "alexa" else "admin_lambda_function"
module_names = [handler_name, "boto3", "botocore"]
if flavor == "alexa":
    module_names += ["ask_sdk_core", "ask_sdk_model"]
for name in module_names:
    module = importlib.import_module(name)
    assert Path(module.__file__).resolve().is_relative_to(root)
assert callable(importlib.import_module(handler_name).lambda_handler)
suite = unittest.TestSuite()
patterns = ["test_backend.py", "test_pin_public.py", "test_session.py"] if flavor == "alexa" else ["test_admin.py"]
for pattern in patterns:
    suite.addTests(unittest.defaultTestLoader.discover(sys.argv[2], pattern=pattern))
result = unittest.TextTestRunner(verbosity=1).run(suite)
if not result.wasSuccessful() or result.testsRun == 0:
    raise SystemExit(1)
print("Handler raiz importable; pruebas offline del ZIP: PASS", result.testsRun)
print(json.dumps({"packaged_test_count": result.testsRun}))
'''
        completed = subprocess.run(
            [sys.executable, "-I", "-B", "-c", code, str(extracted), str(ROOT / "tests"), flavor],
            check=True, text=True, stdout=subprocess.PIPE,
        )
        print(completed.stdout, end="")
        test_count = json.loads(completed.stdout.splitlines()[-1])["packaged_test_count"]
        report = {
            "artifact": destination.name, "runtime": "python3.13", "architecture": "x86_64 (universal pure-Python wheels)",
            "python_build_version": sys.version.split()[0], "zip_bytes": candidate.stat().st_size,
            "uncompressed_bytes": uncompressed, "files": len(entries),
            "sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
            "root_handler": handler_module + ".lambda_handler", "root_handler_import": "PASS",
            "syntax_check": "PASS", "offline_packaged_tests": "PASS", "packaged_test_count": test_count, "secret_file_check": "PASS",
            "real_aws_or_linux_runtime_tested": False,
            "requirements": (ROOT / requirements).read_text().splitlines(),
            "wheels_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT / "build/wheels").glob("*.whl"))},
        }
        os.replace(candidate, destination)
        (destination.parent / report_name).write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({key: report[key] for key in ("zip_bytes", "uncompressed_bytes", "files", "sha256", "root_handler")}, indent=2))
        print("ZIP verificado: " + str(destination))


if __name__ == "__main__":
    main()
