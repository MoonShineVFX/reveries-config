@echo off
echo off

echo ## === Start usdrecord process === ##

set USD_FILEPATH=%1
set USD_IMAGEPATH=%2
set USD_CAMSHAPE=%3
set FRAME_RANGE=%4

set PATH=Q:\Resource\USD-21.02\lib;Q:\Resource\USD-21.02\bin
set PATH=T:\third-party\python27;T:\third-party\python27\Scripts;%PATH%
:: ;%PATH%

set PYTHONPATH=Q:\Resource\USD-21.02\lib\python
:: ;%PYTHONPATH%

echo PATH %PATH%
echo PYTHONPATH %PYTHONPATH%
echo usd file path is %USD_FILEPATH%
echo image path is %USD_IMAGEPATH%

:: set USD_FILEPATH=Q:\199909_AvalonPlay\Avalon\Char\Caterpillar\work\rigging\maya\scenes\review_cache\rig_review_prim.usda
:: set USD_IMAGEPATH=Q:\199909_AvalonPlay\Avalon\Char\Caterpillar\work\rigging\maya\scenes\review_cache\image\v002\###.exr
:: set USD_CAMSHAPE="usd_review_camShape"
:: set FRAME_RANGE="100:105x1"

"Q:\Resource\USD-21.02\bin\usdrecord.cmd" %USD_FILEPATH% %USD_IMAGEPATH% "--camera" %USD_CAMSHAPE% "--frames" %FRAME_RANGE%