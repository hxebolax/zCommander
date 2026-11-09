# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
#
# Reconocimiento de texto con el motor OCR de Windows (Windows.Media.Ocr) desde
# Windows PowerShell 5.1, sin paquetes: es la vía de reserva del complemento
# zc.ocr cuando no se puede usar pywinrt (diseño 2.0, 11.3).
#
# Uso (lo lanza zCommander sin consola):
#   powershell -NoProfile -ExecutionPolicy Bypass -File ocr.ps1 -Idiomas
#   powershell -NoProfile -ExecutionPolicy Bypass -File ocr.ps1 -Entrada <imagen o PDF> [-Idioma es-ES] [-Escala 2]
#
# Escribe UNA línea JSON en UTF-8 por la salida estándar:
#   {"ok":true,"idioma":"es-ES","paginas":[["línea 1","línea 2"],["..."]]}
#   {"ok":true,"idiomas":[{"etiqueta":"es-ES","nombre":"Español (España)"}]}
#   {"ok":false,"codigo":"sin_idiomas","error":"..."}

param(
	[string]$Entrada = "",
	[string]$Idioma = "",
	[double]$Escala = 2.0,
	[switch]$Idiomas
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false

function Json([string]$texto) {
	$sb = New-Object System.Text.StringBuilder
	[void]$sb.Append('"')
	foreach ($c in $texto.ToCharArray()) {
		$n = [int]$c
		if ($c -eq '"') { [void]$sb.Append('\"') }
		elseif ($c -eq '\') { [void]$sb.Append('\\') }
		elseif ($n -lt 32) { [void]$sb.Append(('\u{0:x4}' -f $n)) }
		else { [void]$sb.Append($c) }
	}
	[void]$sb.Append('"')
	return $sb.ToString()
}

function Fallo([string]$codigo, [string]$mensaje) {
	Write-Output ('{"ok":false,"codigo":' + (Json $codigo) + ',"error":' + (Json $mensaje) + '}')
	exit 1
}

try {
	Add-Type -AssemblyName System.Runtime.WindowsRuntime
	$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
	$null = [Windows.Storage.Streams.InMemoryRandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime]
	$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
	$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
	$null = [Windows.Data.Pdf.PdfDocument, Windows.Data.Pdf, ContentType = WindowsRuntime]
	$null = [Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime]
} catch {
	Fallo 'sin_winrt' ('Este Windows no tiene el motor OCR: ' + $_.Exception.Message)
}

$metodos = [System.WindowsRuntimeSystemExtensions].GetMethods()
$comoTarea = $metodos | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } | Select-Object -First 1
$comoTareaAccion = $metodos | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncAction' } | Select-Object -First 1

function Esperar($operacion, [Type]$tipo) {
	$tarea = $comoTarea.MakeGenericMethod($tipo).Invoke($null, @($operacion))
	[void]$tarea.Wait(-1)
	return $tarea.Result
}

function EsperarAccion($accion) {
	$tarea = $comoTareaAccion.Invoke($null, @($accion))
	[void]$tarea.Wait(-1)
}

$disponibles = [Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages
if ($Idiomas) {
	$partes = @()
	foreach ($l in $disponibles) {
		$partes += ('{"etiqueta":' + (Json $l.LanguageTag) + ',"nombre":' + (Json $l.DisplayName) + '}')
	}
	Write-Output ('{"ok":true,"idiomas":[' + ($partes -join ',') + ']}')
	exit 0
}

if (@($disponibles).Count -eq 0) {
	Fallo 'sin_idiomas' 'Windows no tiene ningún idioma con reconocimiento de texto instalado.'
}

if ($Idioma) {
	try {
		$motor = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage((New-Object Windows.Globalization.Language $Idioma))
	} catch {
		$motor = $null
	}
	if ($null -eq $motor) { Fallo 'idioma' ('El idioma ' + $Idioma + ' no tiene reconocimiento de texto instalado.') }
} else {
	$motor = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
	if ($null -eq $motor) { $motor = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage(@($disponibles)[0]) }
}

function Lineas($bitmap) {
	$resultado = Esperar ($motor.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
	$lineas = @()
	foreach ($linea in $resultado.Lines) { $lineas += (Json $linea.Text) }
	return '[' + ($lineas -join ',') + ']'
}

function Mapa($flujo) {
	$decodificador = Esperar ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($flujo)) ([Windows.Graphics.Imaging.BitmapDecoder])
	return Esperar ($decodificador.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
}

try {
	$archivo = Esperar ([Windows.Storage.StorageFile]::GetFileFromPathAsync($Entrada)) ([Windows.Storage.StorageFile])
	$paginas = @()
	if ([System.IO.Path]::GetExtension($Entrada).ToLowerInvariant() -eq '.pdf') {
		$pdf = Esperar ([Windows.Data.Pdf.PdfDocument]::LoadFromFileAsync($archivo)) ([Windows.Data.Pdf.PdfDocument])
		for ($i = 0; $i -lt $pdf.PageCount; $i++) {
			$pagina = $pdf.GetPage($i)
			$flujo = New-Object Windows.Storage.Streams.InMemoryRandomAccessStream
			$opciones = New-Object Windows.Data.Pdf.PdfPageRenderOptions
			$ancho = [Math]::Min([double]([Windows.Media.Ocr.OcrEngine]::MaxImageDimension), $pagina.Size.Width * $Escala)
			$opciones.DestinationWidth = [uint32]$ancho
			EsperarAccion ($pagina.RenderToStreamAsync($flujo, $opciones))
			$paginas += (Lineas (Mapa $flujo))
			$pagina.Dispose()
			$flujo.Dispose()
		}
	} else {
		$flujo = Esperar ($archivo.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
		$paginas += (Lineas (Mapa $flujo))
		$flujo.Dispose()
	}
	Write-Output ('{"ok":true,"idioma":' + (Json $motor.RecognizerLanguage.LanguageTag) + ',"paginas":[' + ($paginas -join ',') + ']}')
	exit 0
} catch {
	Fallo 'error' ($_.Exception.GetBaseException().Message)
}
