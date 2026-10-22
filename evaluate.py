"""Reproduce synthetic evaluation and save auditable evidence."""
from pathlib import Path
from core import train, evaluate

if __name__ == '__main__':
    output=Path(__file__).parent/'evaluation'
    output.mkdir(exist_ok=True)
    metrics, evidence=evaluate(train())
    metrics.to_csv(output/'metrics.csv',index=False)
    evidence.to_csv(output/'labelled_predictions.csv',index=False)
    print(metrics.to_string(index=False))
