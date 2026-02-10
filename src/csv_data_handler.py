"""
CSV Data Handler for Custom Market Data Import

Supports importing OHLCV data from CSV files for backtesting.
"""

import pandas as pd
from datetime import datetime
from typing import Optional


class CSVDataHandler:
    """
    Import and prepare CSV data for backtesting.
    
    Expected CSV format:
    - datetime, open, high, low, close, volume
    - OR: date, time, open, high, low, close, volume
    """
    
    def __init__(self, logger=None):
        self.logger = logger
    
    def load_csv(
        self,
        filepath: str,
        datetime_col: str = 'datetime',
        date_col: Optional[str] = None,
        time_col: Optional[str] = None,
        parse_format: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Load OHLCV data from CSV.
        
        Args:
            filepath: Path to CSV file
            datetime_col: Column name for datetime (if single column)
            date_col: Column name for date (if separate columns)
            time_col: Column name for time (if separate columns)
            parse_format: Custom datetime parse format (e.g., '%Y-%m-%d %H:%M:%S')
        
        Returns:
            DataFrame with datetime index and OHLCV columns
        """
        try:
            # Read CSV
            df = pd.read_csv(filepath)
            
            if self.logger:
                self.logger.info(f"Loaded CSV: {filepath} ({len(df)} rows)")
            
            # Normalize column names
            df.columns = [col.strip().lower() for col in df.columns]
            
            # Parse datetime
            if date_col and time_col:
                # Separate date/time columns
                date_col_lower = date_col.lower()
                time_col_lower = time_col.lower()
                
                if date_col_lower in df.columns and time_col_lower in df.columns:
                    df['datetime'] = pd.to_datetime(
                        df[date_col_lower] + ' ' + df[time_col_lower],
                        format=parse_format
                    )
                else:
                    raise ValueError(f"Columns {date_col}/{time_col} not found")
            
            elif datetime_col.lower() in df.columns:
                # Single datetime column
                df['datetime'] = pd.to_datetime(df[datetime_col.lower()], format=parse_format)
            
            else:
                # Auto-detect datetime column
                datetime_candidates = ['datetime', 'timestamp', 'date', 'time']
                found = False
                
                for col in datetime_candidates:
                    if col in df.columns:
                        df['datetime'] = pd.to_datetime(df[col])
                        found = True
                        break
                
                if not found:
                    raise ValueError("No datetime column found. Specify datetime_col or date_col/time_col")
            
            # Set datetime as index
            df.set_index('datetime', inplace=True)
            df.sort_index(inplace=True)
            
            # Normalize OHLCV column names to title case
            column_mapping = {
                'open': 'Open',
                'high': 'High',
                'low': 'Low',
                'close': 'Close',
                'volume': 'Volume'
            }
            
            df.rename(columns=column_mapping, inplace=True)
            
            # Ensure all OHLCV columns exist
            required_cols = ['Open', 'High', 'Low', 'Close']
            missing = [col for col in required_cols if col not in df.columns]
            
            if missing:
                raise ValueError(f"Missing required columns: {missing}")
            
            # Add Volume if missing
            if 'Volume' not in df.columns:
                df['Volume'] = 0
                if self.logger:
                    self.logger.warning("Volume column not found, filling with zeros")
            
            # Convert to numeric
            for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # Drop NaN rows
            df.dropna(subset=['Open', 'High', 'Low', 'Close'], inplace=True)
            
            # Keep only OHLCV columns
            df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
            
            if self.logger:
                self.logger.info(
                    f"Prepared {len(df)} bars | "
                    f"Period: {df.index[0]} to {df.index[-1]}"
                )
            
            return df
        
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to load CSV: {e}")
            raise
    
    def validate_data(self, df: pd.DataFrame) -> tuple[bool, list]:
        """
        Validate OHLCV data quality.
        
        Returns:
            (is_valid: bool, issues: list)
        """
        issues = []
        
        # Check for gaps in data
        time_diffs = df.index.to_series().diff()
        mode_diff = time_diffs.mode()[0]
        gaps = time_diffs[time_diffs > mode_diff * 2]
        
        if len(gaps) > 0:
            issues.append(f"Found {len(gaps)} time gaps in data")
        
        # Check for invalid OHLC relationships
        invalid_hl = df[df['High'] < df['Low']]
        if len(invalid_hl) > 0:
            issues.append(f"Found {len(invalid_hl)} bars where High < Low")
        
        invalid_oc = df[(df['Open'] > df['High']) | (df['Open'] < df['Low'])]
        if len(invalid_oc) > 0:
            issues.append(f"Found {len(invalid_oc)} bars where Open outside High/Low")
        
        invalid_cc = df[(df['Close'] > df['High']) | (df['Close'] < df['Low'])]
        if len(invalid_cc) > 0:
            issues.append(f"Found {len(invalid_cc)} bars where Close outside High/Low")
        
        # Check for zero/negative prices
        zero_prices = df[(df['Open'] <= 0) | (df['High'] <= 0) | 
                         (df['Low'] <= 0) | (df['Close'] <= 0)]
        if len(zero_prices) > 0:
            issues.append(f"Found {len(zero_prices)} bars with zero/negative prices")
        
        is_valid = len(issues) == 0
        
        if self.logger:
            if is_valid:
                self.logger.info("✅ Data validation passed")
            else:
                self.logger.warning(f"⚠️ Data validation issues:\n" + "\n".join(f"  - {i}" for i in issues))
        
        return is_valid, issues
    
    def resample_timeframe(
        self,
        df: pd.DataFrame,
        timeframe: str
    ) -> pd.DataFrame:
        """
        Resample data to different timeframe.
        
        Args:
            df: Input DataFrame
            timeframe: Target timeframe ('1Min', '5Min', '15Min', '1H', '1D')
        
        Returns:
            Resampled DataFrame
        """
        resampled = df.resample(timeframe).agg({
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum'
        }).dropna()
        
        if self.logger:
            self.logger.info(f"Resampled to {timeframe}: {len(resampled)} bars")
        
        return resampled


# Example usage
if __name__ == "__main__":
    handler = CSVDataHandler()
    
    print("CSV Data Handler - Example Usage")
    print("=" * 70)
    
    # Example CSV formats supported:
    print("\nSupported CSV formats:")
    print("\n1. Single datetime column:")
    print("   datetime,open,high,low,close,volume")
    print("   2024-01-01 09:15:00,23000,23050,22990,23020,1000")
    
    print("\n2. Separate date/time columns:")
    print("   date,time,open,high,low,close,volume")
    print("   2024-01-01,09:15:00,23000,23050,22990,23020,1000")
    
    print("\n3. Timestamp column:")
    print("   timestamp,open,high,low,close,volume")
    print("   1704096900,23000,23050,22990,23020,1000")
    
    print("\n" + "=" * 70)
    print("\nTo use with your data:")
    print("1. Prepare CSV with OHLCV data")
    print("2. Run: from src.csv_data_handler import CSVDataHandler")
    print("3. Load: df = CSVDataHandler().load_csv('your_data.csv')")
    print("4. Use in backtest script")
