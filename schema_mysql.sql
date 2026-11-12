-- =====================================================================
-- K FASHION STORE - Script de Creación de Base de Datos MySQL
-- Basado en el Diagrama de Clases / Entidad-Relación
-- =====================================================================

CREATE DATABASE IF NOT EXISTS kfashion
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE kfashion;

-- Desactivar chequeo de claves foráneas temporalmente para recreación limpia
SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS detalle_venta;
DROP TABLE IF EXISTS abono;
DROP TABLE IF EXISTS venta;
DROP TABLE IF EXISTS compra;
DROP TABLE IF EXISTS variante;
DROP TABLE IF EXISTS prenda;
DROP TABLE IF EXISTS categoria;
DROP TABLE IF EXISTS proveedor;
DROP TABLE IF EXISTS gasto;
DROP TABLE IF EXISTS cliente;
DROP TABLE IF EXISTS usuario;

SET FOREIGN_KEY_CHECKS = 1;

-- ---------------------------------------------------------------------
-- 1. TABLA: usuario
-- ---------------------------------------------------------------------
CREATE TABLE usuario (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL,
    usuario VARCHAR(150) NOT NULL UNIQUE,
    rol ENUM('propietaria', 'vendedora') NOT NULL DEFAULT 'vendedora',
    contrasena VARCHAR(255) NOT NULL,
    debe_cambiar_password BOOLEAN NOT NULL DEFAULT FALSE,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 2. TABLA: cliente
-- ---------------------------------------------------------------------
CREATE TABLE cliente (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    celular VARCHAR(30) NULL,
    ciudad VARCHAR(60) NULL,
    fecha_registro DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 3. TABLA: proveedor
-- ---------------------------------------------------------------------
CREATE TABLE proveedor (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    contacto VARCHAR(30) NULL, -- Teléfono / Celular
    ciudad VARCHAR(60) NULL
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 4. TABLA: categoria
-- ---------------------------------------------------------------------
CREATE TABLE categoria (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(60) NOT NULL UNIQUE
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 5. TABLA: prenda
-- ---------------------------------------------------------------------
CREATE TABLE prenda (
    id INT AUTO_INCREMENT PRIMARY KEY,
    codigo VARCHAR(20) NOT NULL UNIQUE,
    nombre VARCHAR(120) NOT NULL,
    categoria_id INT NOT NULL,
    descripcion TEXT NULL,
    costo DECIMAL(12, 0) NOT NULL DEFAULT 0,
    gastos_presentacion DECIMAL(12, 0) NOT NULL DEFAULT 0,
    margen DECIMAL(5, 1) NOT NULL DEFAULT 50.0,
    precio_venta DECIMAL(12, 0) NOT NULL DEFAULT 0,
    activa BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT fk_prenda_categoria FOREIGN KEY (categoria_id) 
        REFERENCES categoria(id) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 6. TABLA: variante (tallas y colores con stock)
-- ---------------------------------------------------------------------
CREATE TABLE variante (
    id INT AUTO_INCREMENT PRIMARY KEY,
    prenda_id INT NOT NULL,
    talla VARCHAR(10) NOT NULL,
    color VARCHAR(40) NOT NULL,
    cantidad INT NOT NULL DEFAULT 0,            -- Stock actual
    cantidad_minima INT NOT NULL DEFAULT 1,     -- Cantidad mínima para reponer
    proveedor_id INT NULL,
    CONSTRAINT uq_variante UNIQUE (prenda_id, talla, color),
    CONSTRAINT fk_variante_prenda FOREIGN KEY (prenda_id) 
        REFERENCES prenda(id) ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_variante_proveedor FOREIGN KEY (proveedor_id) 
        REFERENCES proveedor(id) ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 7. TABLA: compra (Entrada de mercancía)
-- ---------------------------------------------------------------------
CREATE TABLE compra (
    id INT AUTO_INCREMENT PRIMARY KEY,
    variante_id INT NOT NULL,
    proveedor_id INT NOT NULL,
    fecha DATE NOT NULL,
    cantidad INT NOT NULL,
    valor DECIMAL(12, 0) NOT NULL,
    pagada BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT fk_compra_variante FOREIGN KEY (variante_id) 
        REFERENCES variante(id) ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_compra_proveedor FOREIGN KEY (proveedor_id) 
        REFERENCES proveedor(id) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 8. TABLA: venta
-- ---------------------------------------------------------------------
CREATE TABLE venta (
    id INT AUTO_INCREMENT PRIMARY KEY,
    numero_recibo VARCHAR(20) NOT NULL UNIQUE,
    fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    cliente_id INT NULL,
    usuario_id INT NOT NULL, -- Vendedora o propietaria que registró la venta
    canal ENUM('tienda', 'whatsapp', 'instagram', 'facebook', 'tiktok') NOT NULL DEFAULT 'tienda',
    modalidad ENUM('contado', 'credito') NOT NULL DEFAULT 'contado',
    medio_pago ENUM('efectivo', 'nequi', 'bancolombia', 'daviplata', 'datafono', 'link') NOT NULL DEFAULT 'efectivo',
    comprobante VARCHAR(255) NULL,
    fecha_limite DATE NULL,
    total DECIMAL(12, 0) NOT NULL DEFAULT 0,
    CONSTRAINT fk_venta_cliente FOREIGN KEY (cliente_id) 
        REFERENCES cliente(id) ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_venta_usuario FOREIGN KEY (usuario_id) 
        REFERENCES usuario(id) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 9. TABLA: detalle_venta (Renglones de la venta)
-- ---------------------------------------------------------------------
CREATE TABLE detalle_venta (
    id INT AUTO_INCREMENT PRIMARY KEY,
    venta_id INT NOT NULL,
    variante_id INT NOT NULL,
    cantidad INT NOT NULL,
    precio_unitario DECIMAL(12, 0) NOT NULL,
    CONSTRAINT fk_detalle_venta FOREIGN KEY (venta_id) 
        REFERENCES venta(id) ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_detalle_variante FOREIGN KEY (variante_id) 
        REFERENCES variante(id) ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 10. TABLA: abono (Pagos a ventas a crédito)
-- ---------------------------------------------------------------------
CREATE TABLE abono (
    id INT AUTO_INCREMENT PRIMARY KEY,
    venta_id INT NOT NULL,
    fecha DATE NOT NULL,
    valor DECIMAL(12, 0) NOT NULL,
    medio_pago ENUM('efectivo', 'nequi', 'bancolombia', 'daviplata', 'datafono', 'link') NOT NULL DEFAULT 'efectivo',
    comprobante VARCHAR(255) NULL,
    CONSTRAINT fk_abono_venta FOREIGN KEY (venta_id) 
        REFERENCES venta(id) ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 11. TABLA: gasto
-- ---------------------------------------------------------------------
CREATE TABLE gasto (
    id INT AUTO_INCREMENT PRIMARY KEY,
    fecha DATE NOT NULL,
    usuario_id INT NULL,
    categoria ENUM('mercancia', 'arriendo', 'servicios', 'salario', 'otros') NOT NULL DEFAULT 'otros',
    descripcion VARCHAR(200) NOT NULL,
    monto DECIMAL(12, 0) NOT NULL,
    medio_pago ENUM('efectivo', 'nequi', 'bancolombia', 'daviplata', 'datafono', 'link') NOT NULL DEFAULT 'efectivo',
    es_del_negocio BOOLEAN NOT NULL DEFAULT TRUE, -- TRUE: Negocio, FALSE: Personal
    CONSTRAINT fk_gasto_usuario FOREIGN KEY (usuario_id) 
        REFERENCES usuario(id) ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB;


-- =====================================================================
-- DATOS INICIALES / DEMOSTRACIÓN
-- =====================================================================

-- Usuaria inicial
INSERT INTO usuario (id, nombre, usuario, rol, contrasena, debe_cambiar_password, activo)
VALUES (1, 'Propietaria K Fashion', 'propietaria', 'propietaria', 'kfashion123', FALSE, TRUE);

-- Proveedor de ejemplo
INSERT INTO proveedor (id, nombre, contacto, ciudad)
VALUES (1, 'Confecciones Medellín', '3000000000', 'Medellín');

-- Clienta de ejemplo
INSERT INTO cliente (id, nombre, celular, ciudad)
VALUES (1, 'Clienta de ejemplo', '3100000000', 'Cartagena');

-- Categorías
INSERT INTO categoria (id, nombre) VALUES
(1, 'Enterizos'),
(2, 'Vestidos'),
(3, 'Crop tops'),
(4, 'Faldas');

-- Prendas
INSERT INTO prenda (id, codigo, nombre, categoria_id, descripcion, costo, gastos_presentacion, margen, precio_venta, activa) VALUES
(1, 'KF-0001', 'Enterizo', 1, 'Enterizo elegante', 45000, 1500, 50.0, 89900, TRUE),
(2, 'KF-0002', 'Vestido', 2, 'Vestido casual', 52000, 1500, 50.0, 99900, TRUE),
(3, 'KF-0003', 'Crop top', 3, 'Crop top juvenil', 15000, 1500, 50.0, 39900, TRUE),
(4, 'KF-0004', 'Falda', 4, 'Falda corta', 28000, 1500, 50.0, 64900, TRUE);

-- Variantes (tallas y colores)
INSERT INTO variante (prenda_id, talla, color, cantidad, cantidad_minima, proveedor_id) VALUES
(1, 'S', 'Negro', 5, 2, 1),
(1, 'M', 'Negro', 5, 2, 1),
(1, 'L', 'Negro', 5, 2, 1),
(2, 'S', 'Negro', 5, 2, 1),
(2, 'M', 'Negro', 5, 2, 1),
(2, 'L', 'Negro', 5, 2, 1),
(3, 'S', 'Negro', 5, 2, 1),
(3, 'M', 'Negro', 5, 2, 1),
(3, 'L', 'Negro', 5, 2, 1),
(4, 'S', 'Negro', 5, 2, 1),
(4, 'M', 'Negro', 5, 2, 1),
(4, 'L', 'Negro', 5, 2, 1);

