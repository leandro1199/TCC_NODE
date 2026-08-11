param(
    [string]$CameraIp = "192.168.1.5",
    [string]$Usuario = "admin",
    [ValidateSet("onvif1", "onvif2")]
    [string]$Perfil = "onvif2"
)

$cameraDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonPath = Join-Path $cameraDir "..\.venv-camera\Scripts\python.exe"
$apiPath = Join-Path $cameraDir "api_camera.py"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Ambiente Python não encontrado: $pythonPath"
}

$senhaSegura = Read-Host "Senha RTSP da câmera" -AsSecureString
$senhaPtr = [IntPtr]::Zero

try {
    $senhaPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR(
        $senhaSegura
    )
    $senha = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($senhaPtr)

    $env:CAMERA_MODE = "offline"
    $env:CAMERA_OFFLINE_SOURCE = "rtsp://${CameraIp}:554/${Perfil}"
    $env:CAMERA_RTSP_USER = $Usuario
    $env:CAMERA_RTSP_PASSWORD = $senha
    $env:CAMERA_RTSP_BACKEND = "vlc"

    & $pythonPath $apiPath
    exit $LASTEXITCODE
}
finally {
    if ($senhaPtr -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($senhaPtr)
    }
    Remove-Item Env:CAMERA_RTSP_PASSWORD -ErrorAction SilentlyContinue
}
