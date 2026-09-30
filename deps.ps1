# video-cutout/deps.ps1
# Checks Python packages used for local video background removal.

$ErrorActionPreference = "Stop"
Write-Host "  [video-cutout] Checking dependencies..." -ForegroundColor Cyan

# Keep this tool's Python packages separate from other desktop tools.
$venvDir = Join-Path $PSScriptRoot ".venv"
$python = Join-Path $venvDir "Scripts\python.exe"
if (-not (Test-Path $python)) {
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        throw "Python is missing. Install Python 3.10 or newer and put it on PATH."
    }
    python -m venv $venvDir
    if ($LASTEXITCODE -ne 0) { throw "Could not create the Python virtual environment." }
}

$packages = @(
    @{ Import = "rembg"; Pip = "rembg[gpu]" },
    @{ Import = "cv2"; Pip = "opencv-python" },
    @{ Import = "PIL"; Pip = "pillow" },
    @{ Import = "torch"; Pip = "torch" },
    @{ Import = "onnxruntime"; Pip = "onnxruntime-gpu" },
    @{ Import = "nvidia.cublas"; Pip = "nvidia-cublas-cu12" },
    @{ Import = "nvidia.cuda_runtime"; Pip = "nvidia-cuda-runtime-cu12" },
    @{ Import = "nvidia.cudnn"; Pip = "nvidia-cudnn-cu12" }
)

# Catch optional-import failures inside Python. Native stderr behaves differently
# between Windows PowerShell 5.1 and PowerShell 7 when ErrorActionPreference is Stop.
$importProbe = @'
import importlib
import sys
try:
    importlib.import_module(sys.argv[1])
except Exception:
    sys.exit(1)
print("ok")
'@

foreach ($package in $packages) {
    $ok = & $python -c $importProbe $package.Import
    if ($ok -eq "ok") {
        Write-Host "    OK  $($package.Import)" -ForegroundColor Green
        continue
    }

    Write-Host "    Installing $($package.Pip) via pip..." -ForegroundColor Yellow
    & $python -m pip install $package.Pip
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install $($package.Pip)."
    }
}

if (Test-Path "C:\dev\tools\ffmpeg.exe") {
    Write-Host "    OK  ffmpeg.exe found in C:\dev\tools" -ForegroundColor Green
} elseif (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
    Write-Host "    OK  ffmpeg found on PATH" -ForegroundColor Green
} else {
    Write-Host "    WARN ffmpeg.exe not found. Put it in C:\dev\tools or on PATH." -ForegroundColor Yellow
}

$providers = & $python -c "import onnxruntime as ort; print(','.join(ort.get_available_providers()))" 2>$null
if ($providers -like "*CUDAExecutionProvider*") {
    Write-Host "    OK  ONNX Runtime CUDA provider available" -ForegroundColor Green
} else {
    Write-Host "    WARN ONNX Runtime is not using CUDA. Providers: $providers" -ForegroundColor Yellow
    Write-Host "         Try: .\.venv\Scripts\python.exe -m pip install onnxruntime-gpu" -ForegroundColor Yellow
}

$modelDir = "C:\dev\tools\_models\video-cutout"
$legacyModelDir = "C:\dev\tools\_models\remove-portrait"
# Reuse a complete old download, but send all new downloads to the renamed cache.
if (-not ((Test-Path "$modelDir\RobustVideoMatting" -PathType Container) -and
          (Test-Path "$modelDir\rvm_mobilenetv3.pth" -PathType Leaf)) -and
    (Test-Path "$legacyModelDir\RobustVideoMatting" -PathType Container) -and
    (Test-Path "$legacyModelDir\rvm_mobilenetv3.pth" -PathType Leaf)) {
    $modelDir = $legacyModelDir
}
$rvmRepo = Join-Path $modelDir "RobustVideoMatting"
$rvmWeights = Join-Path $modelDir "rvm_mobilenetv3.pth"
New-Item -ItemType Directory -Force -Path $modelDir | Out-Null

if (Test-Path $rvmRepo) {
    Write-Host "    OK  RobustVideoMatting repo found" -ForegroundColor Green
} elseif (Get-Command git -ErrorAction SilentlyContinue) {
    Write-Host "    Cloning RobustVideoMatting..." -ForegroundColor Yellow
    git clone --depth 1 https://github.com/PeterL1n/RobustVideoMatting.git $rvmRepo
    if ($LASTEXITCODE -eq 0) {
        Write-Host "    OK  RobustVideoMatting cloned" -ForegroundColor Green
    } else {
        throw "Failed to clone RobustVideoMatting."
    }
} else {
    throw "Git is missing. Install Git and rerun deps.ps1 to fetch RobustVideoMatting."
}

if (Test-Path $rvmWeights) {
    Write-Host "    OK  RVM MobileNetv3 weights found" -ForegroundColor Green
} else {
    Write-Host "    Downloading RVM MobileNetv3 weights..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri "https://github.com/PeterL1n/RobustVideoMatting/releases/download/v1.0.0/rvm_mobilenetv3.pth" -OutFile $rvmWeights
    if (Test-Path $rvmWeights) {
        Write-Host "    OK  RVM weights downloaded" -ForegroundColor Green
    } else {
        Write-Host "    ERROR: Failed to download RVM weights" -ForegroundColor Red
    }
}

$cudaTorch = & $python -c "import torch; print(torch.cuda.is_available())" 2>$null
if ($cudaTorch -eq "True") {
    Write-Host "    OK  PyTorch CUDA available" -ForegroundColor Green
} else {
    Write-Host "    WARN PyTorch CUDA is not available; RVM backend will not run" -ForegroundColor Yellow
}
