from app.parsing import parse_and_chunk                                                                 
                                                                                                          
chunks = parse_and_chunk("tests/fixtures", "test_project") 

print(f"총 청크 수: {len(chunks)}")
print(f"청크: {chunks}")