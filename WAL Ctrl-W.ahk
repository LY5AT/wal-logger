#Requires AutoHotkey v2.0
; =====================================================================
;  WAL Logger - Ctrl+W = isvalo ivesta lauka (NE uzdaro narsykles skirtuko)
; =====================================================================
;  Reikia: AutoHotkey v2   ->  https://www.autohotkey.com/   (arba: winget install AutoHotkey.AutoHotkey)
;
;  Naudojimas:
;    1. Idiek AutoHotkey v2.
;    2. Dukart spustelek si faila ("WAL Ctrl-W.ahk") - atsiranda zalia "H" ikona sistemos dekle.
;    3. Atidaryk WAL loggeri narsykleje ir dirbk.
;
;  Veikimas:
;    Kai aktyvus WAL loggerio langas/skirtukas, Ctrl+W nesiunciamas narsyklei
;    (skirtukas neuzsidaro), o vietoj to siunciamas Esc -> loggeris isvalo
;    ivesta Call / Rcv WAL lauka (kaip N1MM Wipe).
;
;  Kituose languose Ctrl+W veikia iprastai (uzdaro skirtuka).
;
;  Pasalinti: desinysis pelės klavikas ant dekle ikonos -> Exit.
;  (Nori, kad startuotu su Windows? Idek nuoroda i shell:startup aplanka.)

SetTitleMatchMode 2          ; "contains" - titulas tures "WAL Contest Logger" bet kur

#HotIf WinActive("WAL Contest Logger")
^w::Send "{Esc}"
#HotIf
