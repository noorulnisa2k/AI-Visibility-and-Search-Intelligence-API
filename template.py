from pathlib import Path

# Base project name
BASE_DIR = Path("ai_visibility_api")

# Folder + file structure definition
STRUCTURE = {
    "app": {
        "__init__.py": "# create_app() factory\n\n\ndef create_app():\n    pass\n",
        "models": {
            "profile.py": "",
            "query.py": "",
            "recommendation.py": "",
        },
        "agents": {
            "base.py": "# optional shared base\n",
            "discovery.py": "# Agent 1\n",
            "scoring.py": "# Agent 2\n",
            "recommendation.py": "# Agent 3\n",
        },
        "api": {
            "profiles.py": "# Blueprint\n",
            "queries.py": "# Blueprint\n",
        },
        "services": {
            "pipeline.py": "# orchestrator\n",
        },
        "utils": {
            "scoring.py": "# opportunity score formula\n",
        },
    },
    "tests": {
        "test_agents.py": "",
    },
    "migrations": {},
    ".env.example": "FLASK_ENV=development\n",
    "docker-compose.yml": "# optional\n",
    "requirements.txt": "",
    "README.md": "# AI Visibility API\n",
}


def create_structure(base_path: Path, structure: dict):
    for name, content in structure.items():
        path = base_path / name

        if isinstance(content, dict):
            # Create directory
            path.mkdir(parents=True, exist_ok=True)
            create_structure(path, content)
        else:
            # Create file
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w") as f:
                f.write(content)


if __name__ == "__main__":
    create_structure(BASE_DIR, STRUCTURE)
    print(f"✅ Project structure created at: {BASE_DIR.resolve()}")