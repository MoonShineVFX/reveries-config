@echo off
echo off

set USDFILEPATH=%1
set PATH=Q:\Resource\USD-21.02\lib;Q:\Resource\USD-21.02\bin;%PATH%
set PATH=T:\third-party\python27\;T:\third-party\python27\Scripts\;%PATH%

set PYTHONPATH=Q:\Resource\USD-21.02\lib\python\;%PYTHONPATH%

echo ##  usd file path is %USDFILEPATH%

"Q:\Resource\USD-21.02\bin\usdview" %USDFILEPATH%