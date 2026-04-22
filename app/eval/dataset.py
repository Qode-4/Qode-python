# QA쌍 (실제 유저가 검색할 법한 질문)

# dataset.py
QA_PAIRS = [
    {
        "query": "jwt token 검증 함수",
        "relevant_keywords": ["jwt", "verify", "token"],
        "ground_truth": "jwt.verify를 사용해서 token을 검증하는 함수가 있다.",
    },
    {
        "query": "회원가입 로그인 기능",
        "relevant_keywords": ["회원가입", "로그인"],
        "ground_truth": "회원가입과 로그인 기능이 있다.",
    },
    {
        "query": "더하기 곱하기 함수",
        "relevant_keywords": ["add", "multiply"],
        "ground_truth": "add와 multiply 함수가 있다.",
    },
]