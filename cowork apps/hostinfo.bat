@echo off
cd /d "D:\Documents\Claude Local\cowork apps"
echo ==== HOSTNAME ==== > hostinfo.txt
hostname >> hostinfo.txt
echo ==== IP CONFIG ==== >> hostinfo.txt
ipconfig /all >> hostinfo.txt
