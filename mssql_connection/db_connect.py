import pyodbc
import pandas as pd
import tomllib
from pathlib import Path

# Load connection string from local secrets2.toml
secrets_path = Path(__file__).parent / "secrets2.toml"
with open(secrets_path, 'rb') as f:
    secrets = tomllib.load(f)
    
# Get connection string from secrets
conn_str = secrets['sql']['conn_str']


# Load SQL query from file
sql_query_path = Path(__file__).parent / 'sql_query.sql'
with open(sql_query_path, 'r') as f:
        query = f.read()
        
# Connect to SQL Server and execute query
with pyodbc.connect(conn_str) as conn:
    df = pd.read_sql_query(query, conn)
    
# Save to CSV (in the same directory as the script)
csv_path = Path(__file__).parent / 'result.csv'
df.to_csv(csv_path, index=False)