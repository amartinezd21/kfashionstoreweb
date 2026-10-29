# K Fashion Store · Control de inventario y finanzas (Django)

Aplicación web basada en el Entregable 1 y 2: inventario por talla y color, ventas de contado y crédito con recibo,
abonos, proveedores, gastos, reportes y balance. Herramientas libres, sin pagos mensuales (RNF-07).

## Puesta en marcha
```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python manage.py makemigrations tienda
python manage.py migrate
python manage.py cargar_demo    # crea usuaria y datos de ejemplo
python manage.py runserver
```
Entrar en http://127.0.0.1:8000 con `propietaria` / `kfashion123` (cámbiala en el botón "Clave").
Para un admin técnico: `python manage.py createsuperuser` y entrar a /admin/.

## Requisitos cubiertos
| Requisito | Dónde |
|---|---|
| RF-01 / RNF-01 usuarios y roles | Menú Vendedoras; la vendedora no ve gastos, reportes ni balance; cambio de clave obligatorio |
| RF-02, RF-15 prendas y precio sugerido | Inventario → Nueva prenda |
| RF-03 entrada de mercancía | Inventario → Entrada de mercancía |
| RF-04 consulta por talla y color | Inventario (buscador) |
| RF-05, 06, 07 ventas, descuento de stock, recibo | Nueva venta → recibo imprimible |
| RF-08, 09 clientas y abonos | Clientas, Ventas → Registrar abono |
| RF-10 proveedores y deudas | Proveedores |
| RF-11 gastos negocio/personales | Gastos |
| RF-12 mínimo y lista por reponer | Inventario → Por reponer |
| RF-13, 14 reporte y balance | Reporte, Balance |
| RNF-02 stock nunca negativo | validación en la venta |
| RNF-03 móvil desde 360 px | Bootstrap responsive |
| RNF-06 respaldo diario | `python manage.py respaldo` (prográmalo con cron) |

## Estructura
- `kfashion/` configuración del proyecto
- `tienda/` aplicación: `models.py`, `views.py`, `forms.py`, `urls.py`, `templates/`
- `media/` comprobantes de pago subidos
