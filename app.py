import io
import base64
import sqlite3
from datetime import datetime
import qrcode
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "llave_secreta_davecars_crud"
DATABASE = "sistema_davecars.db"

# --- CONEXIÓN Y BASE DE DATOS ---
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row  # Permite acceder a columnas por nombre
    return db

def query_db(query, args=()):
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    return [dict(row) for row in rv]  # Convierte cada Row en un diccionario

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        
        # 1. Tabla Usuarios
        cursor.execute('''CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT UNIQUE NOT NULL,
            clave TEXT NOT NULL,
            rol TEXT NOT NULL
        )''')

        # 2. Tabla Almacén
        cursor.execute('''CREATE TABLE IF NOT EXISTS almacen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT UNIQUE NOT NULL,
            nombre TEXT NOT NULL,
            cantidad INTEGER NOT NULL,
            precio REAL NOT NULL
        )''')

        # 3. Tabla Ventas
        cursor.execute('''CREATE TABLE IF NOT EXISTS ventas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente TEXT NOT NULL,
            producto TEXT NOT NULL,
            cantidad INTEGER NOT NULL,
            total REAL NOT NULL,
            fecha TEXT NOT NULL
        )''')

        # 4. Tabla Facturación
        cursor.execute('''CREATE TABLE IF NOT EXISTS facturacion (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero_factura TEXT UNIQUE NOT NULL,
            cliente TEXT NOT NULL,
            fecha TEXT NOT NULL,
            monto REAL NOT NULL,
            estado TEXT NOT NULL
        )''')

        # 5. Tabla Contabilidad
        cursor.execute('''CREATE TABLE IF NOT EXISTS contabilidad (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            descripcion TEXT NOT NULL,
            tipo TEXT NOT NULL,
            monto REAL NOT NULL,
            fecha TEXT NOT NULL
        )''')

        # 6. Tabla RRHH
        cursor.execute('''CREATE TABLE IF NOT EXISTS rrhh (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cedula TEXT UNIQUE NOT NULL,
            nombre TEXT NOT NULL,
            cargo TEXT NOT NULL,
            salario REAL NOT NULL
        )''')

        # Datos por defecto si la base de datos está vacía
        cursor.execute("SELECT COUNT(*) FROM usuarios")
        if cursor.fetchone()[0] == 0:
            cursor.execute(
                "INSERT INTO usuarios (usuario, clave, rol) VALUES (?, ?, ?)",
                ('admin', generate_password_hash('1234'), 'Administrador')
            )
            cursor.execute(
                "INSERT INTO almacen (codigo, nombre, cantidad, precio) VALUES ('REP-001', 'Filtro de Aceite', 25, 12.50)"
            )
            cursor.execute(
                "INSERT INTO rrhh (cedula, nombre, cargo, salario) VALUES ('V-20123456', 'Carlos Mendoza', 'Mecánico jefe', 350.00)"
            )
        
        db.commit()

# --- AUTENTICACIÓN Y SEGURIDAD ---
def verificar_sesion():
    return "usuario" in session

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form.get("usuario")
        clave = request.form.get("clave")
        
        db = get_db()
        user = db.execute("SELECT * FROM usuarios WHERE usuario = ?", (usuario,)).fetchone()
        
        if user and (check_password_hash(user["clave"], clave) or user["clave"] == clave):
            session["usuario"] = user["usuario"]
            session["rol"] = user["rol"]
            return redirect(url_for("almacen"))
        else:
            flash("Credenciales incorrectas", "danger")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# --- MÓDULO 1: ALMACÉN ---
@app.route("/almacen")
def almacen():
    if not verificar_sesion(): return redirect(url_for("login"))
    items = query_db("SELECT * FROM almacen")
    return render_template("almacen.html", items=items)

@app.route("/almacen/guardar", methods=["POST"])
def almacen_guardar():
    if not verificar_sesion(): return redirect(url_for("login"))
    
    item_id = request.form.get("id")
    codigo = request.form.get("codigo")
    nombre = request.form.get("nombre")
    cantidad = request.form.get("cantidad")
    precio = request.form.get("precio")

    db = get_db()
    if item_id:
        db.execute(
            "UPDATE almacen SET codigo=?, nombre=?, cantidad=?, precio=? WHERE id=?",
            (codigo, nombre, cantidad, precio, item_id)
        )
        flash("Producto actualizado correctamente", "success")
    else:
        db.execute(
            "INSERT INTO almacen (codigo, nombre, cantidad, precio) VALUES (?, ?, ?, ?)",
            (codigo, nombre, cantidad, precio)
        )
        flash("Producto registrado correctamente", "success")
        
    db.commit()
    return redirect(url_for("almacen"))

@app.route("/almacen/eliminar/<int:id>")
def almacen_eliminar(id):
    if not verificar_sesion(): return redirect(url_for("login"))
    db = get_db()
    db.execute("DELETE FROM almacen WHERE id = ?", (id,))
    db.commit()
    flash("Producto eliminado correctamente", "warning")
    return redirect(url_for("almacen"))

# --- MÓDULO 2: VENTAS (CON CÓDIGO QR) ---
@app.route("/ventas")
def ventas():
    if not verificar_sesion(): 
        return redirect(url_for("login"))
    
    # 1. Obtener todas las ventas registradas
    ventas_list = query_db("SELECT * FROM ventas ORDER BY id DESC")

    # 2. Filtrar ventas correspondientes al mes y año actual (ejemplo: '2026-03')
    mes_actual = datetime.now().strftime("%Y-%m")
    ventas_mes = query_db("SELECT * FROM ventas WHERE fecha LIKE ?", (f"{mes_actual}%",))

    # 3. Métricas mensuales
    total_monto_mes = sum(float(v["total"]) for v in ventas_mes)
    total_cantidad_ventas = len(ventas_mes)

    # 4. Texto que se convertirá en Código QR
    texto_qr = f"=== DAVECARS - RESUMEN DE VENTAS ===\n"
    texto_qr += f"Período: {datetime.now().strftime('%m/%Y')}\n"
    texto_qr += f"Ventas acumuladas: {total_cantidad_ventas}\n"
    texto_qr += f"Total Recaudado: ${total_monto_mes:.2f}\n"
    texto_qr += f"Fecha de emisión: {datetime.now().strftime('%Y-%m-%d %H:%M')}"

    # 5. Generar QR en memoria y convertir a Base64
    img = qrcode.make(texto_qr)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    qr_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    return render_template(
        "ventas.html",
        ventas=ventas_list,
        qr_base64=qr_base64,
        total_mes=total_monto_mes,
        cant_mes=total_cantidad_ventas,
        mes_nombre=datetime.now().strftime('%B %Y')
    )

@app.route("/ventas/guardar", methods=["POST"])
def ventas_guardar():
    if not verificar_sesion(): return redirect(url_for("login"))
    
    venta_id = request.form.get("id")
    cliente = request.form.get("cliente")
    producto = request.form.get("producto")
    cantidad = request.form.get("cantidad")
    total = request.form.get("total")
    fecha = request.form.get("fecha")

    db = get_db()
    if venta_id:
        db.execute(
            "UPDATE ventas SET cliente=?, producto=?, cantidad=?, total=?, fecha=? WHERE id=?",
            (cliente, producto, cantidad, total, fecha, venta_id)
        )
        flash("Venta actualizada correctamente", "success")
    else:
        db.execute(
            "INSERT INTO ventas (cliente, producto, cantidad, total, fecha) VALUES (?, ?, ?, ?, ?)",
            (cliente, producto, cantidad, total, fecha)
        )
        flash("Venta registrada correctamente", "success")
        
    db.commit()
    return redirect(url_for("ventas"))

@app.route("/ventas/eliminar/<int:id>")
def ventas_eliminar(id):
    if not verificar_sesion(): return redirect(url_for("login"))
    db = get_db()
    db.execute("DELETE FROM ventas WHERE id = ?", (id,))
    db.commit()
    flash("Venta eliminada correctamente", "warning")
    return redirect(url_for("ventas"))

# --- MÓDULO 3: FACTURACIÓN ---
@app.route("/facturacion")
def facturacion():
    if not verificar_sesion(): return redirect(url_for("login"))
    facturas = query_db("SELECT * FROM facturacion ORDER BY id DESC")
    return render_template("facturacion.html", facturas=facturas)

@app.route("/facturacion/guardar", methods=["POST"])
def facturacion_guardar():
    if not verificar_sesion(): return redirect(url_for("login"))
    
    factura_id = request.form.get("id")
    # Acepta tanto numero_factura como num_factura por compatibilidad
    numero_factura = request.form.get("numero_factura") or request.form.get("num_factura")
    cliente = request.form.get("cliente")
    fecha = request.form.get("fecha")
    monto = request.form.get("monto")
    estado = request.form.get("estado")

    if not numero_factura or not numero_factura.strip():
        flash("El número de factura es obligatorio", "danger")
        return redirect(url_for("facturacion"))

    db = get_db()
    try:
        if factura_id:
            db.execute(
                "UPDATE facturacion SET numero_factura=?, cliente=?, fecha=?, monto=?, estado=? WHERE id=?",
                (numero_factura, cliente, fecha, monto, estado, factura_id)
            )
            flash("Factura actualizada correctamente", "success")
        else:
            db.execute(
                "INSERT INTO facturacion (numero_factura, cliente, fecha, monto, estado) VALUES (?, ?, ?, ?, ?)",
                (numero_factura, cliente, fecha, monto, estado)
            )
            flash("Factura registrada correctamente", "success")
            
        db.commit()
    except sqlite3.IntegrityError:
        flash("El número de factura ya existe o no es válido", "danger")

    return redirect(url_for("facturacion"))

@app.route("/facturacion/eliminar/<int:id>")
def facturacion_eliminar(id):
    if not verificar_sesion(): return redirect(url_for("login"))
    db = get_db()
    db.execute("DELETE FROM facturacion WHERE id = ?", (id,))
    db.commit()
    flash("Factura eliminada correctamente", "warning")
    return redirect(url_for("facturacion"))

# --- MÓDULO 4: CONTABILIDAD ---
@app.route("/contabilidad")
def contabilidad():
    if not verificar_sesion(): return redirect(url_for("login"))
    registros = query_db("SELECT * FROM contabilidad ORDER BY id DESC")
    return render_template("contabilidad.html", registros=registros)

@app.route("/contabilidad/guardar", methods=["POST"])
def contabilidad_guardar():
    if not verificar_sesion(): return redirect(url_for("login"))
    
    reg_id = request.form.get("id")
    descripcion = request.form.get("descripcion")
    tipo = request.form.get("tipo")
    monto = request.form.get("monto")
    fecha = request.form.get("fecha")

    db = get_db()
    if reg_id:
        db.execute(
            "UPDATE contabilidad SET descripcion=?, tipo=?, monto=?, fecha=? WHERE id=?",
            (descripcion, tipo, monto, fecha, reg_id)
        )
        flash("Registro contable actualizado", "success")
    else:
        db.execute(
            "INSERT INTO contabilidad (descripcion, tipo, monto, fecha) VALUES (?, ?, ?, ?)",
            (descripcion, tipo, monto, fecha)
        )
        flash("Registro contable guardado", "success")
        
    db.commit()
    return redirect(url_for("contabilidad"))

@app.route("/contabilidad/eliminar/<int:id>")
def contabilidad_eliminar(id):
    if not verificar_sesion(): return redirect(url_for("login"))
    db = get_db()
    db.execute("DELETE FROM contabilidad WHERE id = ?", (id,))
    db.commit()
    flash("Registro eliminado correctamente", "warning")
    return redirect(url_for("contabilidad"))

# --- MÓDULO 5: RECURSOS HUMANOS (RRHH) ---
@app.route("/rrhh")
def rrhh():
    if not verificar_sesion(): return redirect(url_for("login"))
    empleados = query_db("SELECT * FROM rrhh")
    return render_template("rrhh.html", empleados=empleados)

@app.route("/rrhh/guardar", methods=["POST"])
def rrhh_guardar():
    if not verificar_sesion(): return redirect(url_for("login"))
    
    emp_id = request.form.get("id")
    cedula = request.form.get("cedula")
    nombre = request.form.get("nombre")
    cargo = request.form.get("cargo")
    salario = request.form.get("salario")

    db = get_db()
    if emp_id:
        db.execute(
            "UPDATE rrhh SET cedula=?, nombre=?, cargo=?, salario=? WHERE id=?",
            (cedula, nombre, cargo, salario, emp_id)
        )
        flash("Empleado actualizado correctamente", "success")
    else:
        db.execute(
            "INSERT INTO rrhh (cedula, nombre, cargo, salario) VALUES (?, ?, ?, ?)",
            (cedula, nombre, cargo, salario)
        )
        flash("Empleado registrado correctamente", "success")
        
    db.commit()
    return redirect(url_for("rrhh"))

@app.route("/rrhh/eliminar/<int:id>")
def rrhh_eliminar(id):
    if not verificar_sesion(): return redirect(url_for("login"))
    db = get_db()
    db.execute("DELETE FROM rrhh WHERE id = ?", (id,))
    db.commit()
    flash("Empleado eliminado correctamente", "warning")
    return redirect(url_for("rrhh"))

# --- MÓDULO 6: USUARIOS ---
@app.route("/usuarios")
def usuarios():
    if not verificar_sesion(): return redirect(url_for("login"))
    if session.get("rol") != "Administrador":
        flash("Acceso denegado. Solo administradores.", "danger")
        return redirect(url_for("almacen"))
    usuarios_list = query_db("SELECT id, usuario, rol FROM usuarios")
    return render_template("usuarios.html", usuarios=usuarios_list)

@app.route("/usuarios/guardar", methods=["POST"])
def usuarios_guardar():
    if not verificar_sesion(): return redirect(url_for("login"))
    if session.get("rol") != "Administrador":
        flash("Acceso denegado", "danger")
        return redirect(url_for("almacen"))

    user_id = request.form.get("id")
    usuario = request.form.get("usuario")
    clave = request.form.get("clave")
    rol = request.form.get("rol")

    db = get_db()
    if user_id:
        if clave:
            clave_hash = generate_password_hash(clave)
            db.execute("UPDATE usuarios SET usuario=?, clave=?, rol=? WHERE id=?", (usuario, clave_hash, rol, user_id))
        else:
            db.execute("UPDATE usuarios SET usuario=?, rol=? WHERE id=?", (usuario, rol, user_id))
        flash("Usuario actualizado correctamente", "success")
    else:
        clave_hash = generate_password_hash(clave)
        db.execute("INSERT INTO usuarios (usuario, clave, rol) VALUES (?, ?, ?)", (usuario, clave_hash, rol))
        flash("Usuario creado correctamente", "success")

    db.commit()
    return redirect(url_for("usuarios"))

@app.route("/usuarios/eliminar/<int:id>")
def usuarios_eliminar(id):
    if not verificar_sesion(): return redirect(url_for("login"))
    if session.get("rol") != "Administrador":
        flash("Acceso denegado", "danger")
        return redirect(url_for("almacen"))

    db = get_db()
    db.execute("DELETE FROM usuarios WHERE id = ?", (id,))
    db.commit()
    flash("Usuario eliminado correctamente", "warning")
    return redirect(url_for("usuarios"))

# --- ARRANCAR APLICACIÓN ---
if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5500)