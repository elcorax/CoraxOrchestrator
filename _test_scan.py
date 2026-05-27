"""Quick test to verify scan no longer hangs."""
import asyncio
import sys
sys.path.insert(0, ".")
from src.modules.system_scanner import SystemScanner

async def main():
    s = SystemScanner()
    r = await s.scan()
    print(f"CPU cores: {r.hardware.cpu.get('cores')}")
    print(f"Memory GB: {r.hardware.memory.get('total_gb')}")
    print(f"GPUs: {len(r.hardware.gpus)}")
    print(f"Errors: {len(r.errors)}")
    print("SCAN COMPLETED SUCCESSFULLY - NO HANG")

asyncio.run(main())
