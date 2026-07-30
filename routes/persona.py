import json
import logging
from pathlib import Path

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/personas", tags=["persona"])


@router.get("")
async def list_personas():
    try:
        test_file = Path(__file__).parent.parent / "test_personas.py"
        if not test_file.exists():
            return {"personas": []}
        import ast
        with open(test_file, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "PERSONAS":
                        personas = ast.literal_eval(node.value)
                        return {"personas": [{"name": p["name"], "description": p["description"]} for p in personas]}
        return {"personas": []}
    except Exception as e:
        logger.error(f"Failed to load personas: {e}")
        return {"personas": []}
