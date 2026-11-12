import os
import sys
import subprocess

# ==============================================================================
# 프로젝트 빌드 설정 상수
# ==============================================================================
APP_NAME = "Tile BatchProcessor"
APP_PUBLISHER = "YCJ"
APP_URL = "https://github.com/C01000011J01001010/Tile-BatchProcessor"
WORKSPACE_DIR = "_WorkSpace"
ENTRY_SCRIPT = "main.py"

ISS_TEMPLATE = r'''[Setup]
; 프로그램 기본 정보
AppName=__APP_NAME__
AppVersion=__VERSION__
AppPublisher=__APP_PUBLISHER__
AppPublisherURL=__APP_URL__

; 제어판에 표시될 기본 설치 경로
DefaultDirName={autopf}\__APP_NAME__
DisableProgramGroupPage=yes

; 출력될 설치 파일(Setup.exe) 이름
OutputBaseFilename=__SETUP_NAME__
Compression=lzma
SolidCompression=yes

; 관리자 권한 요구
PrivilegesRequired=admin

; 아이콘 설정 (기본 경로)
SetupIconFile=compiler:SetupClassicIcon.ico
UninstallDisplayIcon={app}\__EXE_NAME__.exe

[Files]
Source: "__BASE_DIR__\dist\__EXE_NAME__\__EXE_NAME__.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "__BASE_DIR__\dist\__EXE_NAME__\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; 바탕화면 및 시작 메뉴 바로가기
Name: "{autoprograms}\__APP_NAME__"; Filename: "{app}\__EXE_NAME__.exe"
Name: "{autodesktop}\__APP_NAME__"; Filename: "{app}\__EXE_NAME__.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "바탕화면에 바로가기 만들기"; GroupDescription: "추가 아이콘:"
Name: "contextmenu"; Description: "폴더 우클릭 메뉴에 실행 항목 추가"; GroupDescription: "추가 기능:"; Flags: unchecked

[Registry]
; 1. 폴더를 우클릭했을 때 나타나는 메뉴 (contextmenu 태스크 선택 시 등록)
Root: HKCR; Subkey: "Directory\shell\TileBatchProcessor"; ValueType: string; ValueName: ""; ValueData: "Open __APP_NAME__ Here"; Flags: uninsdeletekey; Tasks: contextmenu
Root: HKCR; Subkey: "Directory\shell\TileBatchProcessor"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\__EXE_NAME__.exe"; Flags: uninsdeletekey; Tasks: contextmenu
Root: HKCR; Subkey: "Directory\shell\TileBatchProcessor\command"; ValueType: string; ValueName: ""; ValueData: """{app}\__EXE_NAME__.exe"" ""%V"""; Flags: uninsdeletekey; Tasks: contextmenu

; 2. 폴더 내부 빈 공간을 우클릭했을 때 나타나는 메뉴 (contextmenu 태스크 선택 시 등록)
Root: HKCR; Subkey: "Directory\Background\shell\TileBatchProcessor"; ValueType: string; ValueName: ""; ValueData: "Open __APP_NAME__ Here"; Flags: uninsdeletekey; Tasks: contextmenu
Root: HKCR; Subkey: "Directory\Background\shell\TileBatchProcessor"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\__EXE_NAME__.exe"; Flags: uninsdeletekey; Tasks: contextmenu
Root: HKCR; Subkey: "Directory\Background\shell\TileBatchProcessor\command"; ValueType: string; ValueName: ""; ValueData: """{app}\__EXE_NAME__.exe"" ""%V"""; Flags: uninsdeletekey; Tasks: contextmenu
'''


def main() -> None:
    print("=" * 60)
    print(f" 🚀 {APP_NAME} 배포 자동화 스크립트 🚀")
    print("=" * 60)

    # 1. 스크립트 위치 기준으로 경로 설정 (_WorkSpace/main.py 검증)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    workspace_path = os.path.join(base_dir, WORKSPACE_DIR)
    entry_point = os.path.join(workspace_path, ENTRY_SCRIPT)

    if not os.path.exists(entry_point):
        print(f"❌ 진입점 스크립트를 찾을 수 없습니다: {entry_point}")
        print(f"   '{WORKSPACE_DIR}' 폴더 아래에 '{ENTRY_SCRIPT}' 및 하위 모듈(models, commands, services, views)이 있는지 확인해주세요.")
        sys.exit(1)

    # 2. 버전 입력 받기
    version = input("👉 출시할 버전을 입력하세요 (예: 1.0.0) : ").strip()
    if not version:
        print("❌ 버전이 입력되지 않아 종료합니다.")
        return

    exe_name = f"Tile_BatchProcessor_v{version}"
    setup_name = f"Tile_BatchProcessor_Setup_v{version}"

    # 3. PyInstaller 실행 (--paths 옵션으로 _WorkSpace 내부 패키지 경로 인식)
    print(f"\n[1/3] PyInstaller 빌드 시작: {exe_name} ...")
    pyinstaller_cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "-w",
        "-n",
        exe_name,
        "--paths",
        workspace_path,
        entry_point,
    ]

    try:
        subprocess.run(pyinstaller_cmd, cwd=base_dir, check=True)
        print("✅ PyInstaller 빌드 성공!")
    except subprocess.CalledProcessError:
        print("❌ PyInstaller 빌드 중 오류가 발생했습니다.")
        sys.exit(1)

    # 4. Inno Setup 스크립트(.iss) 동적 생성
    print("\n[2/3] Inno Setup 스크립트(.iss) 생성 중...")
    iss_content = (
        ISS_TEMPLATE.replace("__APP_NAME__", APP_NAME)
        .replace("__APP_PUBLISHER__", APP_PUBLISHER)
        .replace("__APP_URL__", APP_URL)
        .replace("__VERSION__", version)
        .replace("__EXE_NAME__", exe_name)
        .replace("__SETUP_NAME__", setup_name)
        .replace("__BASE_DIR__", base_dir)
    )
    iss_filename = os.path.join(base_dir, f"build_setup_v{version}.iss")

    with open(iss_filename, "w", encoding="utf-8-sig") as f:
        f.write(iss_content)
    print(f"✅ {os.path.basename(iss_filename)} 생성 완료!")

    # 5. ISCC (Inno Setup Compiler) 실행
    print("\n[3/3] 설치 파일(Setup.exe) 컴파일 시작...")
    iscc_path = r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    if not os.path.exists(iscc_path):
        iscc_path = "iscc"

    try:
        subprocess.run([iscc_path, iss_filename], cwd=base_dir, check=True)
        print("\n" + "=" * 60)
        print("🎉 성공적으로 자동화 빌드가 완료되었습니다!")
        print(f"📁 최종 설치 파일 위치: {os.path.join(base_dir, 'Output', setup_name + '.exe')}")
        print("=" * 60)

        if os.path.exists(iss_filename):
            os.remove(iss_filename)

    except FileNotFoundError:
        print("❌ Inno Setup 컴파일러(ISCC.exe)를 찾을 수 없습니다.")
        print(r"Inno Setup이 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe' 에 설치되어 있는지 확인해주세요.")
    except subprocess.CalledProcessError:
        print("❌ Inno Setup 컴파일 중 오류가 발생했습니다.")


if __name__ == "__main__":
    main()
