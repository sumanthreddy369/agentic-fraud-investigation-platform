"""Create fresh credentials only in the isolated, disposable local proof namespace."""

import json
import secrets
import subprocess

from prove_local_cluster import KUBE, ROOT


def main():
    password = secrets.token_hex(32)
    token = secrets.token_hex(32)
    entries = {
        "risk-database": {
            "POSTGRES_USER": "risk",
            "POSTGRES_DB": "risk",
            "POSTGRES_PASSWORD": password,
        },
        "risk-runtime": {
            "RISK_API_TOKEN": token,
            "RISK_DATABASE_URL": f"postgresql+psycopg://risk:{password}@risk-postgres:5432/risk",
        },
    }
    for name, data in entries.items():
        subprocess.run(
            KUBE + ["create", "-f", "-"],
            input=json.dumps(
                {
                    "apiVersion": "v1",
                    "kind": "Secret",
                    "metadata": {"name": name},
                    "stringData": data,
                }
            ),
            text=True,
            check=True,
            capture_output=True,
        )
    (ROOT / ".test-runtime/proof-token").write_text(token)
    print("Disposable local credentials created; values omitted.")


if __name__ == "__main__":
    main()
