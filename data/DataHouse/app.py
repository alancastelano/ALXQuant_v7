"""DataHouse — RiskSentiment pipeline entry point."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from coletores.RiskSentiment import main as risk_main

def main():
    print("=== DataHouse: RiskSentiment Pipeline ===")
    risk_main()
    print("=== DataHouse: Concluido ===")

if __name__ == "__main__":
    main()
