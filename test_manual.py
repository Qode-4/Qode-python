from app.parsing import parse_and_chunk
from app.embedding.store import reindex

chunks = parse_and_chunk("tests/fixtures", "test_project")
reindex("test_project", chunks)