import pandas as pd
from datetime import datetime, timezone
from companion import explain

def test_offline_guide_missing_and_safety():
    assert 'don’t have a reading' in explain('summary',pd.DataFrame())
    assert 'cannot establish' in explain('Is it safe to drink?',pd.DataFrame())

def test_grounded_answers():
    df=pd.DataFrame([dict(timestamp=datetime.now(timezone.utc).isoformat(),source='simulation',calibrated=0,ph=4.2,turbidity=None,temperature=27,water_level=105,anomaly=1,explanation='Unusual pH.')])
    assert '4.20' in explain('what is pH?',df)
    assert 'unavailable' in explain('turbidity',df)
    assert 'warning' in explain('summary',df)
    assert 'synthetic demonstration' in explain('summary',df)
    assert 'do not confirm pollution' in explain('AI alert',df)
