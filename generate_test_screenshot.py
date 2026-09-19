import sys
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
import random

def make_screenshot(amount=2.0, out_path="test_payment_screenshot.png"):
    now = datetime.now()
    date_str = now.strftime('%d %b %Y')
    time_str = now.strftime('%I:%M %p')
    txn_id = ''.join(random.choices('0123456789', k=12))

    img = Image.new('RGB', (800, 900), color='#ffffff')
    draw = ImageDraw.Draw(img)

    try:
        font_lg = ImageFont.truetype('arial.ttf', 32)
        font_md = ImageFont.truetype('arial.ttf', 24)
    except Exception:
        font_lg = font_md = None

    draw.rectangle([30, 30, 770, 870], fill='#ffffff', outline='#2563eb', width=3)
    draw.rectangle([30, 30, 770, 140], fill='#2563eb')
    draw.text((60, 60), 'Payment Successful', fill='#ffffff', font=font_lg)

    draw.text((60, 180), 'Paid to: Lakshmi Sai Bandi', fill='#000000', font=font_lg)
    draw.text((60, 240), 'UPI ID: lakshmisaibandi@fampay', fill='#333333', font=font_md)
    amt_label = f"Amount: Rs. {amount:.2f}"
    draw.text((60, 300), amt_label, fill='#000000', font=font_lg)
    draw.text((60, 360), f'Date: {date_str}', fill='#333333', font=font_md)
    draw.text((60, 420), f'Time: {time_str}', fill='#333333', font=font_md)
    draw.text((60, 480), f'UPI Transaction ID: {txn_id}', fill='#333333', font=font_md)
    draw.text((60, 540), 'Status: Completed', fill='#059669', font=font_md)

    img.save(out_path)
    print(f"Generated {out_path} for amount Rs. {amount:.2f} at {time_str}")

if __name__ == "__main__":
    amt = float(sys.argv[1]) if len(sys.argv) > 1 else 2.0
    make_screenshot(amt)
