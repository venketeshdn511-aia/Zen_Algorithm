import google.generativeai as genai
import os
import json
import logging
from typing import Dict, Optional

class AiPostMortem:
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.enabled = False
        
        if self.api_key:
            try:
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel('gemini-1.5-flash')
                self.enabled = True
                self.logger.info(" [BRAIN] Gemini AI Post-Mortem initialized (Free Tier)")
            except Exception as e:
                self.logger.error(f" [BRAIN] Gemini init failed: {e}")
        else:
            self.logger.warning(" [BRAIN] GEMINI_API_KEY not found. AI insights disabled.")

    def analyze_trade(self, trade: Dict) -> Optional[Dict]:
        """
        Analyze a completed trade using Gemini.
        """
        if not self.enabled:
            return None
            
        try:
            prompt = self._build_prompt(trade)
            response = self.model.generate_content(prompt)
            
            # Clean response text if it's wrapped in markdown
            text = response.text
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
                
            return json.loads(text)
        except Exception as e:
            self.logger.error(f" [BRAIN] AI Analysis failed: {e}")
            return None

    def _build_prompt(self, trade: Dict) -> str:
        ist_time = trade.get('exit_time', 'Unknown')
        pnl = trade.get('pnl', 0)
        result = "WIN" if pnl > 0 else "LOSS"
        
        prompt = f"""
        Analyze the following algorithmic trade and provide a post-mortem.
        
        TRADE DATA:
        - Strategy: {trade.get('strategy')}
        - Result: {result}
        - PnL: {pnl:.2f}
        - Entry Price: {trade.get('entry')}
        - Exit Price: {trade.get('exit')}
        - Duration: {trade.get('entry_time')} to {ist_time}
        - Exit Reason: {trade.get('reason')}
        - Market Conditions: {json.dumps(trade.get('conditions', {{}}))}
        
        Format your response as a JSON object with strictly these keys:
        - "summary": A one-line summary of the trade.
        - "diagnosis": A 2-3 sentence technical explanation of why this trade happened and why it resulted in a {result}.
        - "insight": One actionable technical refinement for the strategy (e.g., "Widen trailing stop during high ADX").
        - "vibe": A very short (2-3 words) "vibe check" (e.g., "Sharp Reversal", "Patient Capture", "Noise Trap").
        """
        return prompt
