"""El popup de unidades no debe superponer filas al mover el cursor."""

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest

from test_grafico_bombas_ui import app
from ui.constantes import FACTORES_SI
from ui.dialogos import DialogoFluido


@pytest.mark.parametrize('propiedad,presion', [('vap', 2338.46788), ('atm', 101325.0)])
def test_filas_no_se_superponen_y_cada_unidad_es_seleccionable(app, propiedad, presion):
    dialogo = DialogoFluido(1000, 0.001, P_vap=2338.46788)
    dialogo.show()
    combo = getattr(dialogo, 'unidad_' + propiedad)
    campo = getattr(dialogo, 'campo_' + propiedad)
    try:
        # Reabrir después de cada selección también comprueba la caché del popup.
        for fila, unidad in enumerate(dialogo.UNIDADES_PRESION):
            combo.showPopup()
            app.processEvents()
            vista = combo.view()
            rects = [vista.visualRect(vista.model().index(i, 0)) for i in range(combo.count())]
            assert all(r.height() >= 36 for r in rects)
            assert all(a.bottom() < b.top() for a, b in zip(rects, rects[1:]))
            assert all(vista.viewport().rect().contains(r) for r in rects)
            for r in reversed(rects):
                QTest.mouseMove(vista.viewport(), r.center())
            QTest.mouseClick(vista.viewport(), Qt.LeftButton, pos=rects[fila].center())
            assert combo.currentText() == unidad
            assert float(campo.text()) * FACTORES_SI[unidad] == pytest.approx(presion)
        dialogo._validar_y_aceptar()
        rho, mu, patm, pvap = dialogo.valores()
        assert rho == 1000 and mu == 0.001
        assert patm == pytest.approx(101325)
        assert pvap == pytest.approx(2338.46788)
    finally:
        combo.hidePopup()
        dialogo.close()
        dialogo.deleteLater()
