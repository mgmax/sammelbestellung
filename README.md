sammelbestellung
================

A python script for accounting group orders. Order together and save shipping costs!

<h2>Usage</h2>
- Collect order in a standardized text format (see example.txt and example2.txt) 
- Run python sammelbestellung.py your-order.txt
- The script generates:
 - files for importing the total basket
 - the sum every person has to pay (including a part of the shipping cost, relative to the amount of money they spent on goods from each store)
 - a checklist for unpacking the parcel ("How many pieces of this article go to person A?")
- Import the basket into the shops, see if the total sum including shipping is correct
- Start the order
- Use the autmatically generated mail to inform the buyers
- When the parcel arrives, each buyer takes out his things and checks them off on the unpacking list

<h2>Supported shops</h2>
- reichelt.de
- pollin.de
- de.rs-online.com (support currently broken because they changed their interface)
- in the future: de.farnell.com

<h2>Status</h2>
- works fine for reichelt and pollin. Tested on about 10 complicated group orders on different shops with ca. 5 buyers each.
- all calculations use checksums and throw an error if something does not match. Nobody ever complained about calculation errors.
- throws errors, sometimes not completely human-readable ones, when articles are not available. The basket then needs to be fixed (remove the problematic articles) and re-run.

<h2>Example Output</h2>
(only the most interesting parts, input is example.txt)

    ==================================
   	TOTAL SUM
   	==================================
   	Name	total	(items+shipping)
   	bob	25.31	(20.03+5.28)
   	troll	0.92	(0.16+0.76)
   	hering	6.97	(1.21+5.76)
   
   	==================================
   	UNPACKING LIST
   	==================================
   	name     ☒OK   count   (total count)   partNr       shop          
   	bob      ☐     1       (of 3)          PFL 10       reichelt.de   
   	bob      ☐     1                       810 058      pollin.de     
   	troll    ☐     2       (of 3)          PFL 10       reichelt.de   
   	hering   ☐     1                       NE 555 DIP   reichelt.de   
   
   	hering   ☐     1                       SK M3        reichelt.de   

<h2>EML Output</h2>
- your order-file should contain a mail-adress for every buyer
- a .eml-file will be generated
- open in Thunderbird (please contact, if other mailing programms do not work)
- press Ctrl-E to edit as new
<h2>Output into subdirectory</h2>
- add "!subdir true" to your basket-file
- the script will write the output to the directory "filename-output"
- the "!subdir"-cmd is optional an takes the values "true" and "false"