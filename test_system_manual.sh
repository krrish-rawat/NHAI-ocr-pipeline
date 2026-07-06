#!/bin/bash
# Manual system test helper script

echo "======================================================================"
echo "NHAI PDF Parser - Document Validation System Test"
echo "======================================================================"
echo ""

echo "STEP 1: Start the server"
echo "-----------------------------------------------------------------------"
echo "Run this in a separate terminal:"
echo "  cd /Users/krrishrawat/Desktop/NHAI-K/Nhai-pdf-parser"
echo "  uvicorn app:app --reload"
echo ""
read -p "Press ENTER when server is running..."

echo ""
echo "STEP 2: Open the web interface"
echo "-----------------------------------------------------------------------"
echo "Opening browser to http://localhost:8000..."
open http://localhost:8000 2>/dev/null || echo "Open manually: http://localhost:8000"
echo ""
read -p "Press ENTER when page is loaded..."

echo ""
echo "STEP 3: Test with INVALID document"
echo "-----------------------------------------------------------------------"
echo "Actions to perform:"
echo "  1. Upload any PDF (e.g., an invoice, purchase order, or non-NHAI document)"
echo "  2. Enter some field names (e.g., 'contractor_name, date, amount')"
echo "  3. Click 'Extract Data'"
echo ""
echo "EXPECTED RESULT:"
echo "  ⚠️ Amber warning banner appears"
echo "  📄 Banner shows detected document type"
echo "  🔘 Two buttons: 'Upload Correct Document' and 'Force Extract Anyway'"
echo "  ❌ Results panel stays HIDDEN"
echo ""
read -p "Did you see the warning banner? (y/n): " answer
if [ "$answer" = "y" ]; then
    echo "✅ INVALID document validation WORKING"
else
    echo "❌ INVALID document validation FAILED"
    echo ""
    echo "Troubleshooting steps:"
    echo "  1. Open browser console (F12) and check for errors"
    echo "  2. Check Network tab → /extract response for 'document_validity'"
    echo "  3. Verify Gemini API key is configured in .env"
fi

echo ""
echo "STEP 4: Test 'Force Extract Anyway' button"
echo "-----------------------------------------------------------------------"
echo "Click the 'Force Extract Anyway' button"
echo ""
echo "EXPECTED RESULT:"
echo "  ✅ Warning banner disappears"
echo "  ✅ Results panel becomes visible"
echo "  ✅ Extracted data is shown"
echo ""
read -p "Did the results appear? (y/n): " answer
if [ "$answer" = "y" ]; then
    echo "✅ Force extract override WORKING"
else
    echo "❌ Force extract override FAILED"
fi

echo ""
echo "STEP 5: Test 'Upload Correct Document' button"
echo "-----------------------------------------------------------------------"
echo "Refresh the page and repeat STEP 3, then:"
echo "  Click the 'Upload Correct Document' button"
echo ""
echo "EXPECTED RESULT:"
echo "  ✅ Upload form resets"
echo "  ✅ File picker opens"
echo "  ✅ Warning banner clears"
echo ""
read -p "Did the upload reset? (y/n): " answer
if [ "$answer" = "y" ]; then
    echo "✅ Re-upload flow WORKING"
else
    echo "❌ Re-upload flow FAILED"
fi

echo ""
echo "STEP 6: Test with VALID document (LOA/CC/PCC/Financial Closure)"
echo "-----------------------------------------------------------------------"
echo "Upload a valid NHAI document type (if you have one)"
echo ""
echo "EXPECTED RESULT:"
echo "  ✅ NO warning banner"
echo "  ✅ Results render immediately"
echo "  ✅ Data extraction works normally"
echo ""
read -p "Did it work without warnings? (y/n): " answer
if [ "$answer" = "y" ]; then
    echo "✅ VALID document handling WORKING"
else
    echo "⚠️ Note: This might fail if you don't have a real LOA/CC/PCC PDF"
fi

echo ""
echo "======================================================================"
echo "TEST SUMMARY"
echo "======================================================================"
echo ""
echo "If all tests passed, the document validation system is working correctly."
echo ""
echo "For API-level testing, run:"
echo "  curl -X POST http://localhost:8000/extract \\"
echo "    -F 'files=@your_document.pdf' \\"
echo "    -F 'attributes=field1,field2' \\"
echo "    -F 'output_format=json' | jq '.document_validity'"
echo ""
echo "Expected JSON output:"
echo '  {'
echo '    "is_valid": false,'
echo '    "detected_type": "Invoice",'
echo '    "confidence": "high",'
echo '    "message": null'
echo '  }'
echo ""
echo "======================================================================"
