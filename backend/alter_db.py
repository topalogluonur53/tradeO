import sqlite3

def add_columns():
    conn = sqlite3.connect('nexus.db')
    cursor = conn.cursor()
    
    columns_to_add = [
        ("strategy_bollinger_width", "FLOAT", "0.08"),
        ("strategy_rsi_min", "FLOAT", "35.0"),
        ("strategy_rsi_max", "FLOAT", "70.0"),
        ("strategy_volume_multiplier", "FLOAT", "0.6")
    ]
    
    for col, dtype, default in columns_to_add:
        try:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {dtype} DEFAULT {default}")
            print(f"Added {col}")
        except sqlite3.OperationalError as e:
            print(f"Error adding {col} (might exist): {e}")
            
    conn.commit()
    conn.close()

if __name__ == '__main__':
    add_columns()
