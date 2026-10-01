# 🏛️ 오라클 클라우드(OCI) 퀀트 봇 평생 무료 구축 가이드

본 문서는 오라클 클라우드(OCI) Always Free 티어를 이용해 **평생 무료 Linux VM + 영구 고정 공인 IP**를 할당받고, 거래소 IP 등록 후 퀀트 봇을 365일 무인 구동하는 공식 매뉴얼입니다.

---

## 📌 핵심 원칙 (실패 방지)
* **인스턴스 모델**: 반드시 **`VM.Standard.E2.1.Micro` (AMD)**를 선택합니다. (고성능 ARM Ampere A1은 한국 리전에서 99% 용량 부족 에러가 발생하므로 피해야 합니다.)
* **IP 유형**: 인스턴스 생성 직후 기본 유동 IP를 **'예약된 공용 IP(Reserved Public IP)'**로 전환해야 평생 고정됩니다.

---

## 1단계. 인스턴스(VM) 생성
1. [오라클 클라우드 콘솔](https://cloud.oracle.com/) 로그인
2. 메인 화면 중앙 **[VM 인스턴스 생성]** (또는 좌측 상단 햄버거 메뉴 ☰ ➔ **컴퓨트** ➔ **인스턴스** ➔ **[인스턴스 생성]**)
3. **이름**: `quant-bot` 입력
4. **이미지 및 구성 (Image and Shape)**:
   * 이미지: **Canonical Ubuntu 24.04** (또는 22.04)
   * 구성(Shape): **`VM.Standard.E2.1.Micro`** (Always Free 적격 확인)
5. **네트워킹**:
   * 기본값인 **'새 가상 클라우드 네트워크(VCN) 생성'** 및 **'공용 서브넷 생성'** 유지
   * **공용 IPv4 주소 할당**: 반드시 **[예]** 선택
6. **SSH 키 추가 (가장 중요)**:
   * **[자동으로 키 쌍 생성]** 선택
   * 반드시 **[전용 키 저장(Save Private Key)]** 버튼 클릭 ➔ `ssh-key-...key` 파일을 내 PC에 다운로드 (분실 시 접속 불가)
7. 하단 **[생성]** 버튼 클릭 (1~2분 후 주황색에서 녹색 [실행 중]으로 변경됨)

---

## 2단계. 평생 고정 IP(예약된 공용 IP)로 전환
1. 생성된 `quant-bot` 인스턴스 상세 페이지 접속
2. 좌측 하단 리소스 메뉴에서 **[연결된 VNIC]** 클릭 ➔ 표시되는 기본 VNIC 이름 클릭
3. 좌측 리소스 메뉴에서 **[IPv4 주소]** 클릭
4. 표시된 공용 IP 오른쪽 끝의 **점 3개(`...`)** 클릭 ➔ **[편집]**
5. 공용 IP 유형을 **[공용 IP 없음]** 선택 후 [업데이트] (기존 유동 IP 해제)
6. 다시 점 3개(`...`) ➔ **[편집]** ➔ **[예약된 공용 IP(Reserved Public IP)]** 선택 ➔ **[새 예약된 공용 IP 생성]** 선택 ➔ [업데이트]
7. 이제 화면에 표시되는 IP가 **평생 바뀌지 않는 고정 IP**가 됩니다. (IP 주소 복사)

---

## 3단계. 거래소(업비트/빗썸)에 고정 IP 등록
1. **업비트**: [고객센터] ➔ [Open API 관리] ➔ 복사한 오라클 고정 IP 입력 및 추가 인증
2. **빗썸**: [API 관리] ➔ 복사한 오라클 고정 IP 입력 및 추가 인증

---

## 4단계. 서버 접속 및 봇 설치
1. 내 PC의 PowerShell을 열고 다운로드한 SSH 키 파일이 있는 폴더에서 접속:
   ```powershell
   ssh -i <다운로드한_키파일이름>.key ubuntu@<오라클_고정_IP>
   ```
2. 오라클 서버 내부에서 패키지 및 봇 다운로드:
   ```bash
   sudo apt update && sudo apt install -y python3-pip git
   git clone https://github.com/haksoo0918/quant-bitcoin.git
   cd quant-bitcoin
   pip install -r requirements.txt --break-system-packages
   nano .env
   # .env 내용(API 키, 웹훅) 붙여넣기 후 Ctrl+O, Enter, Ctrl+X로 저장
   ```
3. 매일 아침 09:05 KST 자동 실행 크론 등록:
   ```bash
   crontab -e
   # 맨 아래 한 줄 추가:
   5 9 * * * cd /home/ubuntu/quant-bitcoin && python3 src/main.py --live >> /home/ubuntu/bot.log 2>&1
   ```
