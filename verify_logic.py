import os
from datetime import datetime
from app import calcular_horas_trabalhadas, get_feriados

def test_logic():
    print("Iniciando testes de lógica de feriados e horas extras...")

    # Testa a função get_feriados
    feriados_2024 = get_feriados(2024)
    print(f"Feriados encontrados em 2024: {len(feriados_2024)}")
    if "2024-01-01" in feriados_2024:
        print("OK: 01/01/2024 identificado como feriado.")
    if "2024-12-17" in feriados_2024:
        print("OK: 17/12/2024 identificado como feriado municipal.")

    # Testa o cálculo de horas extras 100% em feriado
    func_map = {"1": "João"}

    # Caso 1: Feriado (01/01/2024 - Segunda)
    registros_feriado = [
        ("1", datetime(2024, 1, 1, 8, 0)),
        ("1", datetime(2024, 1, 1, 12, 0))
    ]
    resumo_feriado = calcular_horas_trabalhadas(registros_feriado, func_map)
    print(f"Resultado em feriado (esperado 100%): {resumo_feriado['João']}")

    # Caso 2: Dia normal (02/01/2024 - Terça)
    registros_normal = [
        ("1", datetime(2024, 1, 2, 8, 0)),
        ("1", datetime(2024, 1, 2, 12, 0))
    ]
    resumo_normal = calcular_horas_trabalhadas(registros_normal, func_map)
    print(f"Resultado em dia normal (esperado Normal): {resumo_normal['João']}")

    # Caso 3: Domingo (07/01/2024)
    registros_domingo = [
        ("1", datetime(2024, 1, 7, 8, 0)),
        ("1", datetime(2024, 1, 7, 12, 0))
    ]
    resumo_domingo = calcular_horas_trabalhadas(registros_domingo, func_map)
    print(f"Resultado em domingo (esperado 100%): {resumo_domingo['João']}")

if __name__ == "__main__":
    test_logic()
