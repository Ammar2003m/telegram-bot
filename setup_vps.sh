#!/bin/bash
# سكريبت تثبيت البوت على VPS
# الاستخدام: bash setup_vps.sh

set -e

echo "📦 تثبيت المكتبات..."
pip3 install -r requirements.txt

echo "📁 إنشاء مجلد البيانات..."
mkdir -p data

echo "🌐 تثبيت Playwright..."
python3 -m playwright install chromium --with-deps 2>/dev/null || echo "⚠️ Playwright: اختياري"

echo ""
echo "✅ التثبيت اكتمل!"
echo ""
echo "📋 الخطوات التالية:"
echo "  1. انسخ ملف store.db إلى مجلد data/"
echo "  2. شغّل البوت: python3 main.py"
echo ""
echo "⚙️ لتشغيل تلقائي مع systemd:"
echo "  sudo cp storerozbot.service /etc/systemd/system/"
echo "  sudo systemctl enable storerozbot"
echo "  sudo systemctl start storerozbot"
