from datetime import datetime, timedelta
import pytz

def get_next_nifty_expiry():
    """
    Calculates the next Thursday expiry date for Nifty options.
    Logic:
    - If today is Thursday and time < 15:30, expiry is today.
    - If today is Thursday and time >= 15:30, expiry is next Thursday.
    - Else find next Thursday.
    
    Returns:
        str: Expiry code (YYMMM or YYMdd) compatible with Broker
    """
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    
    # Monday=0, Tuesday=1, ... Thursday=3, ... Sunday=6
    # Target Thursday (weekday=3)
    target_weekday = 3
    current_weekday = now.weekday()
    
    if current_weekday == target_weekday:  # Today is Thursday
        # Check if market close time has passed (3:30 PM)
        if now.hour > 15 or (now.hour == 15 and now.minute >= 30):
            days_ahead = 7  # Move to next Thursday
        else:
            days_ahead = 0  # Today is expiry
    else:
        # Days until next Thursday
        days_ahead = (target_weekday - current_weekday + 7) % 7
        if days_ahead == 0: days_ahead = 7
            
    expiry_date = now + timedelta(days=days_ahead)
            
    expiry_date = now + timedelta(days=days_ahead)
    
    # Check if this Tuesday is the LAST Tuesday of the month (Monthly Expiry)
    # Logic: If adding 7 days puts us in the next month, it's the last Tuesday
    next_week = expiry_date + timedelta(days=7)
    is_monthly_expiry = next_week.month != expiry_date.month
    
    if is_monthly_expiry:
        # Monthly expiry format: YYMMM (e.g., 26JAN)
        return expiry_date.strftime("%y%b").upper()
    else:
        # Weekly expiry format: YYMdd
        yy = str(expiry_date.year)[2:]
        month = expiry_date.month
        dd = f"{expiry_date.day:02d}"
        
        # Fyers Month codes: 1-9, O (Oct), N (Nov), D (Dec)
        m_code = str(month)
        if month == 10: m_code = "O"
        elif month == 11: m_code = "N"
        elif month == 12: m_code = "D"
        
        return f"{yy}{m_code}{dd}"

