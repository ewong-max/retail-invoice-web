# Retail Invoice - Web version

Simple invoicing for a small walk-in retail shop (Python + Flask + SQLite, PDFs with reportlab).
The screens run in the web browser.
`RetailInvoiceWeb.exe` starts a small web server on this PC only (http://127.0.0.1:5080) and opens the browser.

## Run from source
```
python -m pip install flask waitress reportlab
python app.py
```

## Package for the client (no Python needed on their PC)
Double-click `build.bat`. Output:

    %USERPROFILE%\Downloads\RetailInvoiceWeb\RetailInvoiceWeb.exe

Exact command it runs:
```
python -m PyInstaller --noconfirm --clean --console --name RetailInvoiceWeb --add-data "templates;templates" --distpath "%USERPROFILE%\Downloads" --workpath build --specpath build app.py
```
Copy the whole `RetailInvoiceWeb` folder to the client PC; make a desktop shortcut to the exe.

## Daily use
- Double-click the shortcut: a black window opens (that is the app's engine) and the browser opens the invoice page.
  Keep the black window open (minimise it). Closing it shuts the app down.
- Double-clicking again while it's running just opens another browser tab.
- Type items straight into the table; Enter moves to a new row. Ctrl+S saves.
- Print opens the browser's print dialog. Export PDF downloads the PDF to the Downloads folder.
- Invoice History: search (number, customer, or date as dd/mm/yyyy), Open/Edit, Reprint, PDF, Cancel.

## Data (on each PC)
`Documents\RetailInvoicesWeb\`
- `invoices.db` - all invoices (back this file up)
- `shop_details.txt` - shop name (line 1) and address lines; edit in Notepad, then restart the app

## Dev notes
- `RETAIL_INVOICE_DATA` env var overrides the data folder; `NO_BROWSER=1` stops the browser opening (used for testing).
- Templates are cached; restart the app after editing them.
