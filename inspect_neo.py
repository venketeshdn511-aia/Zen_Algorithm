
from neo_api_client import NeoAPI
import inspect

print("Dir(NeoAPI):")
print(dir(NeoAPI))

print("\nInit Signature:")
try:
    print(inspect.signature(NeoAPI.__init__))
except Exception as e:
    print(f"Could not get signature: {e}")

print("\nHelp(NeoAPI):")
try:
    help(NeoAPI)
except: pass
