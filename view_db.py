#!/usr/bin/env python3
"""
Visualizador simples do banco Arena Marina - SEM DEPENDÊNCIAS
"""
import sqlite3

DB_PATH = "arena_marina.db"

def print_table(name, columns, rows):
    """Imprime tabela formatada sem bibliotecas externas"""
    print(f"\n🗂️  TABELA: {name.upper()}")
    print("-" * 80)
    
    if not rows:
        print("(vazia)")
        return
    
    # Calcular largura das colunas
    col_widths = [len(str(col)) for col in columns]
    for row in rows:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(val)))
    
    # Cabeçalho
    header = " | ".join(str(col).ljust(col_widths[i]) for i, col in enumerate(columns))
    print(header)
    print("-" * 80)
    
    # Linhas
    for row in rows:
        line = " | ".join(str(val).ljust(col_widths[i]) for i, val in enumerate(row))
        print(line)
    
    print(f"\n✓ Total: {len(rows)} registro(s)")

def main():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Listar todas as tabelas
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
        tables = [row[0] for row in cursor.fetchall()]
        
        print("\n" + "="*80)
        print("📊 BANCO DE DADOS: Arena Marina")
        print("="*80)
        
        for table in tables:
            if table.startswith("sqlite_"):  # Pular tabelas internas
                continue
                
            cursor.execute(f"SELECT * FROM {table}")
            columns = [description[0] for description in cursor.description]
            rows = cursor.fetchall()
            print_table(table, columns, rows)
        
        print("\n" + "="*80 + "\n")
        conn.close()
    except Exception as e:
        print(f"❌ Erro: {e}")

if __name__ == "__main__":
    main()
