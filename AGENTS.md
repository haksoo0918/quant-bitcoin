# 🤖 Workspace Agent Rules (`AGENTS.md`)

이 규칙은 `quant-bitcoin` 프로젝트 내 모든 AI 작업에 항상 적용됩니다.

---

## 📌 Git 커밋 및 변경 이력(CHANGELOG) 작성 원칙

1. **커밋 승인 시 체인지로그 선작성 필수**:
   - 사용자로부터 Git 커밋 진행 승인을 받더라도 **절대 곧바로 `git commit`을 실행하지 않습니다.**
   - 커밋 승인이 나면 **1순위로 `CHANGELOG.md`를 열어 이번 작업의 변경 내역(Added / Changed / Fixed 등)을 먼저 작성·갱신**합니다.
   
2. **동반 일괄 커밋 집행**:
   - `CHANGELOG.md` 갱신이 완료된 것을 확인한 후, 코드/문서 변경사항과 `CHANGELOG.md`를 함께 스테이징(`git add`)하여 최종 `git commit` 및 `git push`를 진행합니다.
