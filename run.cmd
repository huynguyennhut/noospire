@echo off
rem Thin wrapper: the only supported local launcher is run.ps1 (API + gateway on loopback).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*
