# 🏛️ 오라클 클라우드(OCI) 퀀트 봇 평생 무료 구축 가이드

본 문서는 오라클 클라우드(OCI) Always Free 티어를 이용해 **평생 무료 Linux VM + 영구 고정 공인 IP**를 할당받고, 거래소 IP 등록 후 퀀트 봇을 365일 무인 구동하는 공식 매뉴얼입니다.

---

## 📌 핵심 원칙 (실패 방지)
* **인스턴스 모델**: 반드시 **`VM.Standard.E2.1.Micro` (AMD)**를 선택합니다. (ARM Ampere A1은 리전 품귀 에러가 잦으므로 피해야 합니다.)
* **IP 유형**: 인스턴스 생성 직후 기본 VNIC의 **[IP 관리]** 탭에서 **'예약된 퍼블릭 IP(Reserved Public IP)'**로 발급/연결해야 평생 고정됩니다.

---

## 💡 비전공자를 위한 핵심 용어 1분 정리 (쉬운 비유)
* **인스턴스 (Instance / VM)**: 오라클 데이터센터에 있는 **'24시간 켜진 가상 컴퓨터 본체'**입니다. 내 PC를 꺼도 이 가상 컴퓨터는 계속 켜져 있습니다.
* **VCN (가상 클라우드 네트워크)**: 우리 집의 **'유무선 공유기 망'**과 같습니다. 가상 컴퓨터들이 통신하기 위한 독립된 가상 네트워크 공간입니다.
* **서브넷 (Subnet)**: 집 안의 **'방(구역)'**입니다. 외부 인터넷과 자유롭게 통신할 수 있는 방을 **'퍼블릭 서브넷'**이라고 부릅니다.
* **VNIC (가상 네트워크 인터페이스 카드)**: 컴퓨터 본체 뒤에 꽂는 **'랜카드(랜선 포트)'** 부품입니다.
* **예약된 퍼블릭 IP (Reserved Public IP)**: 서버를 껐다 켜도 절대 바뀌지 않는 **'평생 고정 집주소'**입니다. 업비트/빗썸에 등록해두면 이 주소에서 오는 주문만 안전하게 통과시켜 줍니다.
* **SSH 키 (`.key` 파일)**: 비밀번호 대신 쓰는 **'디지털 열쇠'**입니다. 이 열쇠 파일이 있어야만 서버 터미널에 로그인할 수 있습니다. (현재 PC 보관 위치: `~/.ssh/ssh-key-2026-10-02.key`)
* **크론탭 (Crontab)**: 리눅스 컴퓨터의 **'자동 알람 시계'**입니다. "매일 아침 09:05가 되면 봇을 실행해라"처럼 정해진 시간에 프로그램을 자동 실행합니다.
* **스왑 (Swap)**: 램(RAM)이 부족할 때 하드디스크의 일부를 임시 메모리로 빌려 쓰는 **'비상용 보조 램'**입니다.

---

## 1단계. 인스턴스(VM) 생성 (완료)
1. **오라클 클라우드 콘솔** 로그인 (리전: 도쿄 `ap-tokyo-1` 또는 서울)
2. 메인 화면 **[VM 인스턴스 생성]** 클릭
3. **이름**: `instance-quant-bot-20261002` (또는 원하는 이름)
4. **배치**: 가용성 도메인 기본값, 용량 유형: `주문형(On-demand)` 기본값 유지
5. **보안**: 기본값 유지
6. **이미지 및 구성 (Image and Shape)**:
   * 이미지: **Canonical Ubuntu 24.04**
   * 구성(Shape): **`VM.Standard.E2.1.Micro`** (Always Free 적격)
7. **기본 VNIC 및 네트워킹**:
   * 기본 네트워크: **`새 가상 클라우드 네트워크 생성`** (`vcn-20261002-xxxx`)
   * 서브넷: **`새 퍼블릭 서브넷 생성`** (`subnet-20261002-xxxx`, CIDR `10.0.0.0/24`)
   * VNIC 이름: `quant-bot-vnic`
   * 퍼블릭 IPv4 주소 지정: 비활성화 상태 그대로 유지 (2단계에서 예약 고정 IP로 부여)
8. **SSH 키 추가**:
   * **`자동으로 키 쌍 생성`** 선택
   * 반드시 **`[프라이빗 키 다운로드]`** 클릭 ➔ 다운로드 후 PC의 표준 SSH 경로에 보관:
     * 보관 위치: `~/.ssh/ssh-key-2026-10-02.key` (분실 시 서버 재접속 불가)
9. **스토리지**: 기본 부트 볼륨(약 47GB) 유지 ➔ 하단 **`[생성]`** 클릭
10. 상태가 주황색에서 녹색 **[실행 중]**으로 변경 확인.

---

## 2단계. 평생 고정 IP(예약된 공용 IP) 할당 (완료)
1. 인스턴스 상세 화면 상단 가로 탭에서 **`[네트워킹]`** 탭 클릭
2. 기본 VNIC 이름(**`quant-bot-vnic`**) 클릭
3. VNIC 화면 상단 가로 탭 중 두 번째 **`[IP 관리]`** 탭 클릭
4. 프라이빗 IP 행 오른쪽 끝의 **점 3개(`...`)** 클릭 ➔ **`[편집]`**
5. 모달 창 입력:
   * 퍼블릭 IP 유형: **`예약된 퍼블릭 IP`** 선택
   * 라디오 버튼: **`새 예약된 IP 생성`** 선택
   * 퍼블릭 IP 이름: `quant-bot-ip` 입력
   * **IP 주소 소스**: 드롭다운에서 **`Oracle`** 반드시 선택
   * 경로 테이블: **`VCN, 서브넷 또는 VNIC 경로 테이블 사용`** (기본값)
6. 하단 **`[업데이트]`** 클릭
7. 발급된 영구 고정 공인 IP 확인: **`<내_고정_IP> (예약됨)`**

---

## 3단계. 거래소(업비트/빗썸) 고정 IP 등록 (완료)
1. **업비트**:
   * [고객센터] ➔ [Open API 관리] ➔ API Key 수정
   * 허용 IP 주소란에 **`<내_고정_IP>`** 등록 및 추가 인증 완료.
2. **빗썸**:
   * [고객센터] ➔ [API 관리] ➔ API Key 관리
   * 허용 IP 주소란에 **`<내_고정_IP>`** 등록 및 추가 인증 완료.

---

## 4단계. 서버 접속 (Cloud Shell 활용) (완료)
* 로컬 인터넷(통신사/공유기)에서 22번 포트(SSH) 아웃바운드가 차단된 경우, OCI 웹 콘솔 내장 **Cloud Shell**로 우회 접속:
1. OCI 웹 콘솔 우측 상단 `>_` 아이콘(Cloud Shell) 클릭.
2. Cloud Shell 상단 톱니바퀴/메뉴 ➔ **[파일 업로드]** ➔ PC의 키 파일(`~/.ssh/ssh-key-2026-10-02.key`) 업로드.
3. Cloud Shell 터미널에서 권한 수정 및 서버 접속:
   ```bash
   chmod 600 ssh-key-2026-10-02.key
   ssh -i ssh-key-2026-10-02.key ubuntu@<내_고정_IP>
   ```
4. 프롬프트가 `ubuntu@quant-bot-vnic:~$`로 변경되면 접속 성공.

---

## 5단계. 서버 환경 구축 및 봇 설치 (완료)
1. **스왑 메모리(1GB) 생성 및 패키지 설치**:
   ```bash
   sudo fallocate -l 1G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
   sudo apt update && sudo apt install -y python3-pip git
   ```
2. **봇 소스코드 클론 및 라이브러리 설치**:
   ```bash
   git clone https://github.com/haksoo0918/quant-bitcoin.git
   cd quant-bitcoin
   pip install -r requirements.txt --break-system-packages
   ```
3. **환경변수(`.env`) 설정**:
   ```bash
   cat << 'EOF' > .env
   UPBIT_ACCESS_KEY=your_key
   UPBIT_SECRET_KEY=your_key
   BITHUMB_ACCESS_KEY=your_key
   BITHUMB_SECRET_KEY=your_key
   DISCORD_WEBHOOK_URL=your_url
   EOF
   ```

---

## 6단계. 실거래 통신 검증 (완료)
* 모의 실행을 통해 고정 IP 화이트리스트 및 디스코드 알림 테스트:
  ```bash
  python3 src/main.py --dry-run
  ```
* **검증 결과**:
  * 업비트/빗썸 API 통신 성공 (`<내_고정_IP>` 인가 확인).
  * 디스코드 모의 주문 알림 수신 완료.

---

## 7단계. 365일 무인 자동화 스케줄링 등록 (완료)
1. **서버 시계 한국 표준시(KST) 동기화**:
   ```bash
   sudo timedatectl set-timezone Asia/Seoul
   ```
2. **크론탭(Crontab) 등록 (매일 09:05 KST 실행)**:
   ```bash
   (crontab -l 2>/dev/null; echo "5 9 * * * cd /home/ubuntu/quant-bitcoin && /usr/bin/python3 src/main.py --live >> /home/ubuntu/quant-bitcoin/cron.log 2>&1") | crontab -
   ```
3. **등록 확인**: `crontab -l` 실행 시 `5 9 * * * ...` 출력 확인.

---

## 8단계. 데스크톱(로컬 PC) 기존 스케줄러 삭제 (완료)
* 중복 실행 및 PC 전원 의존 방지를 위해 Windows 작업 스케줄러에서 로컬 작업 해제:
  * 대상 작업: `QuantCryptoLiveTrader`
  * 조치: 완전히 삭제(Unregister) 완료.

---

## 9단계. 운영 및 모니터링 방법
* **로그 확인**: 서버 접속 후 언제든지 실행 로그 실시간 확인 가능:
  ```bash
  cat /home/ubuntu/quant-bitcoin/cron.log
  # 또는 실시간 모니터링:
  tail -f /home/ubuntu/quant-bitcoin/cron.log
  ```
* **PC/브라우저 상태**: 이제 PC를 끄거나 오라클 클라우드 브라우저 창을 닫아도 365일 자동 구동됩니다.

---

## 10단계. 코드 수정 시 무인 자동 배포 (GitHub Actions CD)
* **원리**: PC에서 봇 코드를 수정한 뒤 깃허브에 푸시하면, 깃허브 액션이 ①단위 테스트(`pytest`) 전수 검증 ➔ ②오라클 서버에 SSH 접속하여 `git pull` ➔ ③모의실행(`--dry-run`)까지 완전 자동으로 마칩니다.
* **1회 사전 설정 (GitHub Secrets 등록)**:
  1. GitHub 저장소 상단 **[Settings]** ➔ 좌측 **[Secrets and variables]** ➔ **[Actions]** 이동.
  2. **[New repository secret]** 클릭 후 아래 3개 등록:
     * `ORACLE_HOST`: 오라클 고정 공인 IP (`<내_고정_IP>`)
     * `ORACLE_USER`: `ubuntu`
     * `ORACLE_SSH_KEY`: PC에 보관된 키 파일(`~/.ssh/ssh-key-2026-10-02.key`)의 내용 전체 텍스트 복사하여 붙여넣기.
* **효과**: 이제 코드를 수정할 때 오라클 콘솔에 접속할 필요 없이, PC에서 `git push`만 하면 서버 배포까지 원클릭으로 끝납니다.
