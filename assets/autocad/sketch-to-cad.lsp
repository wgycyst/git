;;; sketch-to-cad.lsp -- helpers for tracing a hand-drawn sketch in AutoCAD 2024
;;; Loaded automatically via acaddoc.lsp in the Support folder, or with APPLOAD.
;;; Prompts are ASCII on purpose: LISP files are read in the system code page.
;;;
;;; Commands
;;;   S2CLAYERS  create S2C-BASE / S2C-TRACE / S2C-DIM and fade the base layer
;;;   S2CIMG     attach the sketch photo as an underlay on S2C-BASE
;;;   S2CINSERT  insert a traced DXF produced by sketch2cad.py as a block
;;;   S2CSTART   tracing mode: object snaps tuned for tracing
;;;   S2CEND     restore the snap settings saved by S2CSTART
;;;   S2CHELP    command list

(vl-load-com)

(defun s2c:doc () (vla-get-ActiveDocument (vlax-get-acad-object)))
(defun s2c:layers () (vla-get-Layers (s2c:doc)))
(defun s2c:say (s) (princ (strcat "\n[S2C] " s)))

(defun s2c:has-layer (n)
  (not (vl-catch-all-error-p (vl-catch-all-apply 'vla-item (list (s2c:layers) n)))))

(defun s2c:mklayer (n color)
  (if (not (s2c:has-layer n))
    (let ((l (vla-add (s2c:layers) n)))
      (vl-catch-all-apply 'vla-put-Color (list l color))))
  n)

(defun s2c:fade (n alpha)
  (vl-catch-all-apply 'vla-put-Transparency (list (vla-item (s2c:layers) n) alpha)))

(defun c:S2CLAYERS ()
  (s2c:mklayer "S2C-BASE" 8)
  (s2c:mklayer "S2C-TRACE" 3)
  (s2c:mklayer "S2C-DIM" 1)
  (s2c:fade "S2C-BASE" 120)
  (s2c:say "layers ready: S2C-BASE (photo, faded) / S2C-TRACE (green) / S2C-DIM (red)")
  (princ))

(defun c:S2CIMG ( / f pt img)
  (if (/= 1 (getvar "TILEMODE"))
    (s2c:say "run this command on the Model tab, not in a layout.")
    (progn
      (setq f (getfiled "Select the hand-drawn sketch (photo/scan)" "" "jpg;jpeg;png;bmp;tif;tiff" 0))
      (if f
        (progn
          (c:S2CLAYERS)
          (setq pt (getpoint "\nInsertion point <0,0>: "))
          (if (not pt) (setq pt '(0 0)))
          (setq img (vl-catch-all-apply 'vla-AddRaster
                      (list (vla-get-ModelSpace (s2c:doc)) (vlax-3d-point pt) f 1.0 0.0)))
          (if (vl-catch-all-error-p img)
            (s2c:say (strcat "attach failed: " (vl-catch-all-error-message img)))
            (progn
              (vl-catch-all-apply 'vla-put-Layer (list img "S2C-BASE"))
              (s2c:say "underlay attached on S2C-BASE.")
              (s2c:say "now set the real size: SCALE -> select -> base point -> R -> two points on the drawing -> type the real length.")
              (s2c:say "then draw over it and keep every traced object on S2C-TRACE."))))
        (s2c:say "no file selected."))))
  (princ))

(defun c:S2CINSERT ( / f ins)
  (setq f (getfiled "Select the traced DXF" "" "dxf" 0))
  (if f
    (progn
      (c:S2CLAYERS)
      (setq ins (getpoint "\nInsertion point <0,0>: "))
      (if (not ins) (setq ins '(0 0)))
      (setvar "CMDECHO" 0)
      (command "_-INSERT" f ins 1 1 0)
      (setvar "CMDECHO" 1)
      (s2c:say "DXF inserted as a block. EXPLODE it to get plain polylines."))
    (s2c:say "no file selected."))
  (princ))

(defun c:S2CSTART ()
  (setq *s2c-osmode* (getvar "OSMODE"))
  (setq *s2c-ortho* (getvar "ORTHOMODE"))
  (setq *s2c-osm* "on")
  (setvar "OSMODE" 4775)
  (setvar "ORTHOMODE" 0)
  (s2c:say "tracing mode: snaps = endpoint/midpoint/center/intersection/perpendicular/nearest/extension")
  (princ))

(defun c:S2CEND ()
  (if *s2c-osmode* (setvar "OSMODE" *s2c-osmode*))
  (if *s2c-ortho* (setvar "ORTHOMODE" *s2c-ortho*))
  (setq *s2c-osmode* nil)
  (s2c:say "object snap settings restored.")
  (princ))

(defun c:S2CHELP ()
  (princ "\n[S2C] commands:")
  (princ "\n  S2CIMG     attach the hand-drawn photo as an underlay (layer S2C-BASE)")
  (princ "\n  S2CINSERT  insert a traced DXF from sketch2cad.py as a block")
  (princ "\n  S2CLAYERS  create S2C-BASE / S2C-TRACE / S2C-DIM")
  (princ "\n  S2CSTART   tracing mode (object snap setup)")
  (princ "\n  S2CEND     restore object snap settings")
  (princ "\n  SCALE by reference: SCALE -> select -> base point -> R -> pick 2 points -> real length")
  (princ "\n  sketch-to-cad.lsp v1.0")
  (princ))

(princ "\n[S2C] sketch-to-cad tools loaded. Type S2CHELP.")
(princ)
