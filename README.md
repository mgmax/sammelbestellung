sammelbestellung
================

A python script for accounting group orders. Order together and save shipping costs!

Usage:
- Collect order in a standardized text format (see example.txt) 
- Run python sammelbestellung.py your-order.txt
- The script generates:
 - files for importing the total basket
 - the sum every person has to pay (including a part of the shipping cost, relative to the amount of money they spent on goods from each store)
 - a checklist for unpacking the parcel ("How many pieces of this article go to person A?")
- Import the basket into the shops, see if the total sum including shipping is correct
- Start the order
- When the parcel arrives, each buyer takes out his things and checks them off on the unpacking list

Supported shops
- reichelt.de
- pollin.de
- de.rs-online.com (support currently broken because they changed their interface)
- in the future: de.farnell.com

Status:
- works fine for reichelt and pollin. Tested on about 10 complicated group orders on different shops with ca. 5 buyers each.
- all calculations use checksums and throw an error if something does not match. Nobody ever complained about calculation errors.
- throws errors, sometimes not completely human-readable ones, when articles are not available. The basket then needs to be fixed (remove the problematic articles) and re-run.
