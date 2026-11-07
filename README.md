# ONE PIECE LIFE — OpenAI GM / Render 버전

기존 공개형 채팅 RPG MVP의 **AI 연결부만 OpenAI API로 교체**했습니다. RunPod/vLLM/GPU 서버는 필요하지 않습니다.

## 기능 유지
- 기존 한국어 채팅 UI, 회원가입/로그인, 계정별 SQLite 세이브 및 대화 기록
- 종족/진영/경로/질문/이름 캐릭터 생성, 종합 전투력, 레벨업
- NPC 행동 제안 및 기록, 개인 퀘스트, 원작 사건 분기 기록
- 기존 master_rules.txt 및 extension_rules.txt 포함

## Render 배포 (기존 Web Service를 갱신)
1. 이 폴더 **안의 모든 파일**을 GitHub 저장소 루트에 업로드/덮어쓰기하고 커밋합니다. ZIP 자체를 업로드하지 마세요.
2. Render > 기존 **Web Service** > Settings에서 GitHub 저장소, branch=main, Runtime=Docker를 확인합니다. **Blueprint를 선택하지 않습니다.**
3. Render > Environment에서 아래 변수를 설정합니다.
   - `OPENAI_API_KEY` = OpenAI Platform에서 발급한 실제 비밀 키
   - `OPENAI_MODEL` = `gpt-4.1-mini` (접근 가능한 모델로 변경 가능)
   - `COOKIE_SECURE` = `true`
   - `DATABASE_PATH` = `/data/game.sqlite3` (**/data 영구 디스크가 연결된 경우에만**). 영구 디스크가 없다면 DB 경로를 설정하지 말고 테스트만 진행하세요. 재배포/재시작 시 데이터가 소실될 수 있습니다.
4. 기존의 `AI_BASE_URL`, `AI_MODEL`, `AI_API_KEY` 변수는 제거합니다.
5. Render > Manual Deploy > Deploy latest commit. 상태가 Live면 주소를 열어 테스트합니다.

OpenAI API 키를 **GitHub, HTML, 클라이언트 JS에 넣지 마세요.** API 이용료는 ChatGPT 구독료와 별도로 청구됩니다.

## 로컬 테스트
`pip install -r requirements.txt` 후 `OPENAI_API_KEY` 환경 변수를 설정하고 `uvicorn app:app --reload` 실행.

## 중요한 제약
이 버전은 기존 MVP를 보존한 AI 제공자 교체본입니다. NPC의 지속적인 백그라운드 자율 시뮬레이션, 전체 원작 연표, 완전한 전투 규칙은 아직 구현되지 않았습니다. AI가 제안한 수치 변화는 서버에서 상한을 제한하지만 완전한 결정론적 전투 판정은 아닙니다.

공개 서비스 전에는 요청량 제한, 가입 남용 방지, 예산 제한, CSRF 보호, 영구 DB/백업, 운영 보안 점검이 필요합니다. SQLite는 소규모 MVP 테스트용입니다. 원피스 팬 프로젝트의 저작권/상표도 확인하세요.

## 등장인물 스테이터스 정리
- 확장 규칙에서 루피·조로·나미·우솝의 고정 능력치/종합전투력/잠재력 표를 삭제했습니다.
- 기존 주인공의 고정 초기 스테이터스는 사용하지 않습니다.
- 능력치 산정·성장·전투력 평가 규칙은 유지하며, 캐릭터별 수치는 각 캠페인에서 생성·계산합니다.
- 과거 고정 수치가 포함된 `extension_rules_original.txt` 파일은 배포본에서 제거했습니다.
- 이미 서버 DB에 저장된 캐릭터의 수치는 자동 삭제하지 않습니다.
