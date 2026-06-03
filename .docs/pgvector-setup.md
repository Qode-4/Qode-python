# pgvector 설치 가이드

## 왜 필요한가

이 프로젝트는 코드 청크 임베딩을 PostgreSQL의 `vector(1536)` 컬럼에 저장하고, pgvector의 `<=>` 연산자로 유사도 검색을 수행합니다.

따라서 `DATABASE_URL`이 가리키는 PostgreSQL 서버에 pgvector extension이 설치되어 있어야 합니다. PostgreSQL extension은 서버 버전별 디렉터리에 설치되므로, PostgreSQL 16을 사용한다면 pgvector도 PostgreSQL 16이 인식하는 위치에 설치되어야 합니다.

## 설치 여부 확인

DBeaver 또는 psql에서 앱이 사용하는 DB에 접속한 뒤 실행합니다.

```sql
SELECT name, default_version, installed_version
FROM pg_available_extensions
WHERE name = 'vector';
```

결과가 없으면 PostgreSQL 서버에 pgvector가 설치되지 않은 상태입니다.

`installed_version`이 비어 있으면 서버에는 설치되어 있지만 현재 DB에는 extension이 활성화되지 않은 상태입니다.

## DB별 extension 활성화

pgvector 설치 후, 앱이 사용하는 DB마다 한 번씩 실행합니다.

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
```

이 프로젝트는 서버 기동 시 `code_embeddings` 테이블과 인덱스를 자동 생성하지만, `vector` extension 자체는 PostgreSQL 서버에 설치되어 있어야 합니다.

## macOS, PostgreSQL 16

Homebrew의 `pgvector` 패키지가 현재 실행 중인 PostgreSQL 버전에 맞지 않는 경우가 있습니다. 예를 들어 PostgreSQL 16은 실행 중인데 pgvector가 PostgreSQL 17/18용 경로에만 설치되면 `vector.control`을 찾지 못합니다.

PostgreSQL 16용으로 직접 빌드합니다.

```bash
cd /tmp
git clone --branch v0.8.2 https://github.com/pgvector/pgvector.git
cd pgvector

make clean

make PG_CONFIG=/usr/local/opt/postgresql@16/bin/pg_config \
  PG_SYSROOT=$(xcrun --show-sdk-path)

make install PG_CONFIG=/usr/local/opt/postgresql@16/bin/pg_config \
  PG_SYSROOT=$(xcrun --show-sdk-path)
```

설치 후 확인합니다.

```bash
ls /usr/local/opt/postgresql@16/share/postgresql@16/extension/vector.control
ls /usr/local/opt/postgresql@16/lib/postgresql/vector.dylib
```

필요하면 PostgreSQL을 재시작합니다.

```bash
brew services restart postgresql@16
```

## Windows 로컬, PostgreSQL 16, Docker 없이

전제 조건:

- PostgreSQL 16이 Windows에 설치되어 있어야 합니다.
- Visual Studio Build Tools가 필요합니다.
- 설치 시 `Desktop development with C++` 워크로드를 포함합니다.

Visual Studio Build Tools:

```text
https://visualstudio.microsoft.com/visual-cpp-build-tools/
```

`x64 Native Tools Command Prompt for VS`를 관리자 권한으로 실행합니다.

```bat
cd %TEMP%
git clone --branch v0.8.2 https://github.com/pgvector/pgvector.git
cd pgvector

set "PGROOT=C:\Program Files\PostgreSQL\16"

nmake /F Makefile.win
nmake /F Makefile.win install
```

PostgreSQL을 다른 경로에 설치했다면 `PGROOT` 값을 실제 설치 경로로 바꿉니다.

설치 후 DBeaver 또는 psql에서 앱이 사용하는 DB에 접속해 extension을 활성화합니다.

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
```

## Ubuntu, PostgreSQL 16

PostgreSQL 공식 APT 저장소(PGDG)를 사용하는 경우:

```bash
sudo apt update
sudo apt install -y postgresql-common
sudo /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh

sudo apt update
sudo apt install -y postgresql-16-pgvector
```

설치 후 앱이 사용하는 DB에서 extension을 활성화합니다.

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
```

패키지가 없거나 직접 빌드해야 하는 경우:

```bash
sudo apt update
sudo apt install -y build-essential git postgresql-server-dev-16

git clone --branch v0.8.2 https://github.com/pgvector/pgvector.git
cd pgvector

make PG_CONFIG=/usr/lib/postgresql/16/bin/pg_config
sudo make install PG_CONFIG=/usr/lib/postgresql/16/bin/pg_config
```

그 다음 앱이 사용하는 DB에서 extension을 활성화합니다.

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
```

## 자주 발생하는 오류

### extension "vector" is not available

PostgreSQL 서버가 pgvector를 인식하지 못하는 상태입니다.

주요 원인:

- pgvector가 설치되지 않았습니다.
- PostgreSQL 16을 쓰는데 pgvector가 다른 PostgreSQL 버전 경로에 설치되었습니다.
- DBeaver가 다른 PostgreSQL 서버 또는 다른 포트에 연결되어 있습니다.

확인:

```sql
SELECT name, default_version, installed_version
FROM pg_available_extensions
WHERE name = 'vector';
```

### vector.control: No such file or directory

PostgreSQL이 바라보는 extension 디렉터리에 `vector.control` 파일이 없습니다.

macOS PostgreSQL 16 기준 확인:

```bash
/usr/local/opt/postgresql@16/bin/pg_config --sharedir
ls /usr/local/opt/postgresql@16/share/postgresql@16/extension/vector.control
```

### stdio.h file not found

macOS에서 pgvector를 소스 빌드할 때 SDK 경로가 맞지 않으면 발생할 수 있습니다.

PostgreSQL 16의 `pg_config`가 없는 SDK를 가리키는지 확인합니다.

```bash
/usr/local/opt/postgresql@16/bin/pg_config --cppflags
xcrun --show-sdk-path
```

빌드 시 `PG_SYSROOT`를 현재 SDK로 덮어 실행합니다.

```bash
make PG_CONFIG=/usr/local/opt/postgresql@16/bin/pg_config \
  PG_SYSROOT=$(xcrun --show-sdk-path)
```

### CREATE EXTENSION 권한 부족

DB 계정에 extension 생성 권한이 없으면 관리자 계정으로 먼저 실행해야 합니다.

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
```
