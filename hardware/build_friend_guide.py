"""Build the printable, source-linked friend setup pack; no hardware access."""
from pathlib import Path
import sys
from html import escape
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, Table, TableStyle
from reportlab.graphics.shapes import Drawing, Rect, Line, String, Circle
from reportlab.graphics import renderPDF, renderSVG

ROOT=Path(__file__).resolve().parent
OUT=ROOT.parent/'output'/'pdf'
OUT.mkdir(parents=True,exist_ok=True)
INK=colors.HexColor('#15313a'); MUTED=colors.HexColor('#47616b')
PURPLE=colors.HexColor('#6553ad'); GREEN=colors.HexColor('#197864'); RED=colors.HexColor('#a24736')
PALE=colors.HexColor('#f0f6f5'); LINE=colors.HexColor('#cedbdc')
pdf=OUT/'RiverGuard-Friend-Setup.pdf'
c=canvas.Canvas(str(pdf),pagesize=landscape(A4))
c.setTitle('RiverGuard - Wiring and first real readings')
c.setAuthor('RiverGuard')
styles={
 'body':ParagraphStyle('body',fontName='Helvetica',fontSize=10.5,leading=14.5,textColor=INK,spaceAfter=7),
 'small':ParagraphStyle('small',fontName='Helvetica',fontSize=9,leading=12,textColor=MUTED),
 'code':ParagraphStyle('code',fontName='Courier',fontSize=8.3,leading=11,textColor=INK),
}
y=0
page=0
def header(title,sub='',wide=False):
 global y,page
 page+=1
 size=landscape(A4) if wide else A4
 c.setPageSize(size); w,h=size
 c.setFillColor(PALE);c.rect(0,h-96,w,96,fill=1,stroke=0)
 c.setFillColor(PURPLE);c.setFont('Helvetica-Bold',9);c.drawString(36,h-27,'RIVERGUARD / FRIEND SETUP')
 c.setFillColor(INK);c.setFont('Helvetica-Bold',22);c.drawString(36,h-55,title)
 c.setFillColor(MUTED);c.setFont('Helvetica',10);c.drawString(36,h-75,sub)
 y=h-115
def footer():
 w,h=c._pagesize
 c.setStrokeColor(LINE);c.line(36,33,w-36,33)
 c.setFont('Helvetica',8);c.setFillColor(MUTED)
 c.drawString(36,20,'NodeMCU-32S | 21 Oct 2026 | Bench setup; verify on the physical hardware')
 c.drawRightString(w-36,20,f'{page} / 8');c.showPage()
def p(text,style='body',gap=7):
 global y
 obj=Paragraph(text,styles[style]);w,h=obj.wrap(c._pagesize[0]-72,760)
 assert y-h>42,(page,text[:80],y,h)
 obj.drawOn(c,36,y-h);y-=h+gap
def heading(text):
 global y
 y-=5;c.setFillColor(PURPLE);c.setFont('Helvetica-Bold',13);c.drawString(36,y-12,text);y-=24
def code(text):
 p('<br/>'.join(escape(line).replace(' ','&nbsp;') for line in text.splitlines()),'code',10)
def note(text):
 p('<b>Check before continuing:</b> '+text)
def table(rows,widths=None):
 global y
 data=[[Paragraph(escape(str(v)),styles['small']) for v in row] for row in rows]
 t=Table(data,colWidths=widths or [130,393-0],hAlign='LEFT')
 t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),PALE),('VALIGN',(0,0),(-1,-1),'TOP'),('BOX',(0,0),(-1,-1),.5,LINE),('INNERGRID',(0,0),(-1,-1),.35,LINE),('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
 tw,th=t.wrap(c._pagesize[0]-72,760);assert y-th>42,(page,y,th)
 t.drawOn(c,36,y-th);y-=th+11

# Diagram uses native vector primitives, not a generated image of wiring.
d=Drawing(770,425)
def txt(x,y,text,size=10,color=INK,bold=False):
 d.add(String(x,y,text,fontName='Helvetica-Bold' if bold else 'Helvetica',fontSize=size,fillColor=color))
def wire(x1,y1,x2,y2,color=PURPLE,width=2):d.add(Line(x1,y1,x2,y2,strokeColor=color,strokeWidth=width))
def resistor(x,y,vertical=False,label='10k ohm'):
 if vertical:
  d.add(Rect(x-5,y,10,22,fillColor=colors.white,strokeColor=INK,strokeWidth=1.2));txt(x+10,y+7,label,9)
 else:
  d.add(Rect(x,y-5,48,10,fillColor=colors.white,strokeColor=INK,strokeWidth=1.2));txt(x-2,y+11,label,9)
def ground(x,y):
 wire(x,y,x,y-6,INK,1.3)
 for i,width in enumerate([14,9,4]):wire(x-width/2,y-6-i*4,x+width/2,y-6-i*4,INK,1.2)
def card(y,title,power,extra):
 d.add(Rect(555,y,205,73,rx=10,ry=10,fillColor=PALE,strokeColor=LINE))
 txt(567,y+53,title,12,bold=True);txt(567,y+35,power,10,GREEN if '3V3' in power else RED)
 txt(567,y+20,'GND -> common GND',9);txt(567,y+7,extra,8.8)
d.add(Rect(0,0,770,425,fillColor=colors.white,strokeColor=None))
d.add(Rect(8,28,182,371,rx=14,ry=14,fillColor=PALE,strokeColor=LINE))
txt(23,375,'NodeMCU-32S',16,bold=True);txt(23,356,'USB-C from laptop',11)
txt(23,338,'Use GPIO numbers,',9);txt(23,324,'not header positions.',9)
txt(23,43,'GND -> common GND',10,bold=True)
txt(215,385,'Power: ESP32 via USB-C; regulated 5 V for the two 5 V sensors.',10,bold=True)
txt(215,369,'Never join 5 V to 3V3. See page 2 for the supply and meter checks.',10,MUTED)
for yy,label in [(300,'GPIO34  <- pH A'),(220,'GPIO35  <- turbidity A'),(140,'GPIO27  <-> DS18B20 DQ'),(95,'GPIO5    -> TRIG'),(64,'GPIO18  <- ECHO')]:
 # Last port is drawn below main controller body, clearly labelled.
 txt(23,yy+5,label,10,bold=True);d.add(Circle(190,yy,3,fillColor=PURPLE,strokeColor=None))
card(274,'SEN0161-V2 / pH','VCC (+) -> ESP32 3V3','A (0-3.0 V) -> GPIO34; probe -> BNC')
wire(190,300,555,300);txt(300,310,'Direct signal; verify V2 board',10)
card(194,'SEN0189 / cloudiness','VCC -> regulated 5 V rail','Select ANALOG mode; A -> divider')
wire(190,220,405,220);d.add(Circle(365,220,3,fillColor=PURPLE,strokeColor=None))
resistor(405,220);wire(453,220,555,220)
txt(465,232,'sensor A',9);wire(365,220,365,195);resistor(365,173,True,'15k ohm');ground(365,173)
txt(219,234,'ADC junction',9);txt(215,180,'4.5 V in -> 2.7 V here',9)
card(114,'DS18B20 / temperature','VDD -> ESP32 3V3','Use cable labels / supplier pinout')
wire(190,140,555,140);d.add(Circle(485,140,3,fillColor=PURPLE,strokeColor=None))
wire(485,140,485,155);resistor(485,155,True,'4.7k ohm');wire(485,177,485,187);txt(460,191,'ESP32 3V3',9,GREEN)
card(21,'JSN-SR04T / distance','VCC -> verified 5 V rail','Confirm revision + trigger/echo mode')
wire(190,95,535,95);wire(535,95,535,76);wire(535,76,555,76);txt(380,102,'TRIG: verify 3.3 V accepted',9)
wire(190,64,405,64);resistor(405,64);wire(453,64,555,64)
d.add(Circle(365,64,3,fillColor=PURPLE,strokeColor=None));wire(365,64,365,50);resistor(365,28,True,'15k ohm');ground(365,28)
txt(230,77,'GPIO junction',9);txt(466,76,'ECHO',9);txt(215,35,'5.0 V in -> 3.0 V here',9)
txt(10,407,'Signals shown below. Each sensor card also lists its power and ground connections.',10,MUTED)
txt(10,2,'All GND symbols, sensor GND, ESP32 GND and 5 V supply negative must join.',9,bold=True)

header('Wire the station', 'Logical connections - not a physical board pin layout. Disconnect power before changing wires.',True)
renderPDF.draw(d,c,36,57)
footer()
if '--pdf-only' not in sys.argv:
 renderSVG.drawToFile(d,str(ROOT/'RiverGuard-Wiring.svg'))

header('1 / Prepare and connect', 'Start with one sensor at a time. Keep the electronics dry.')
heading('Have these on the table')
p('NodeMCU-32S, USB data cable, the four confirmed sensors, breadboard or terminals, jumper wires, multimeter, regulated 5 V sensor supply, <b>two 10k + two 15k ohm resistors (1%)</b>, and one <b>4.7k ohm resistor</b>. Also prepare certified pH buffers, turbidity standards, a ruler and reference thermometer. TDS is not required.')
heading('A. Power plan')
p('<b>ESP32:</b> power from the laptop through USB-C. Its 3V3 pin powers the V2 pH conditioner and externally powered DS18B20. Verify the board regulator and total load against its documentation.')
p('<b>5 V sensor rail:</b> use a regulated supply suitable for SEN0189 and your JSN revision. Join its negative to ESP32 GND. Do not connect that 5 V rail to 3V3, or to the ESP32 5V/VIN pin while USB is attached. This avoids assuming your USB-C board has backfeed protection.')
heading('B. Make two identical voltage dividers')
code('Sensor output ---- 10k ---- junction ---- ESP32 input\n                              |\n                             15k\n                              |\n                             GND')
p('Divider 1: <b>SEN0189 A -> GPIO35</b>. Divider 2: <b>JSN ECHO -> GPIO18</b>. Do not swap the resistors: the 15k goes from the junction to GND. The ESP32 connects at that junction, never at the sensor output.')
p('Junction voltage = input x 15 / (10 + 15) = input x 0.6. Nominal 4.5 V becomes 2.7 V; 5.0 V becomes 3.0 V. Use separate resistor pairs for the two signals.')
note('Before attaching GPIO35/18, verify each divider with a known DC input and meter. Disconnect the sensor signal for that test; do not feed 5 V into a sensor output. A meter on a pulsed ECHO can show an average rather than its peak; use a scope if checking the actual waveform. Confirm the protected peak stays within ESP32 limits.')
heading('C. Connect the remaining signals')
p('pH V2 A -> GPIO34; pH probe -> conditioner BNC. DS18B20 DQ -> GPIO27 and <b>4.7k from DQ to 3V3</b>. JSN TRIG -> GPIO5. Verify that this JSN revision accepts 3.3 V triggering; otherwise use a suitable one-way level shifter. GPIO5 is a boot strapping pin, so check that the attached module does not force the wrong startup level. Confirm cable functions; never guess them by colour.')
footer()

header('2 / First connection to the app', 'Use the supplied RiverGuard folder. Do not run from inside its ZIP.')
heading('1. Get the laptop receiver running')
p('Install Python 3.14 with PATH enabled, then double-click <b>Setup RiverGuard.cmd</b>. Next run <b>Start RiverGuard.cmd</b>; it opens a trusted laptop session at port 8501. Keep the launcher open. Ollama is only needed for Rill chat, not sensor readings.')
p('Use the same private Wi-Fi. Run <b>ipconfig</b> to find the laptop Wi-Fi IPv4 address. From another device, <b>http://LAPTOP_IP:8000/health</b> should report status ok. Port 8000 receives authenticated sensor packets; 8501 serves the app. Check private firewall rules and Wi-Fi client isolation if blocked. Do not expose either port to the internet.')
heading('2. Register the station and download its private file')
p('On the laptop, open <b>Sensors &gt; Connect</b>. Enter the firmware station ID and select <b>Register new station</b>. Enter the 2.4 GHz Wi-Fi name/password and laptop receiver URL. Select <b>Download station_config.h</b> and put the file in <b>hardware/firmware/include</b>. Check the GPIO assignments before uploading.')
code('API_URL: "http://LAPTOP_IP:8000/api/v1/readings"\nDEVICE_ID: your registered station ID\nAPI_TOKEN: generated private station credential')
p('The file also contains your Wi-Fi details. Keep it private and retain a secure copy; the token is shown once. An existing station keeps its original file. Old firmware without API_TOKEN needs this one authenticated upload. All probes initially stay disabled.')
heading('3. Build and upload once')
p('Install VS Code with PlatformIO IDE and open <b>hardware/firmware</b>. Allow internet access and several GB for its pinned tools. Use Build, Upload and Serial Monitor. With PlatformIO Core CLI, these commands run from the app root:')
code('pio run --project-dir hardware/firmware\npio run --project-dir hardware/firmware --target upload\npio device monitor --baud 115200')
p('For multiple ports, add <b>--upload-port COMx</b> or monitor <b>--port COMx</b>. Close Serial Monitor before uploading. Wi-Fi, URL, pins or a replaced token require another upload; routine calibration does not.')
heading('4. Confirm the first packet')
p('At 115200 baud, expect a JSON sample and <b>Receiver status: 201</b> after NTP sync. In <b>Sensors &gt; Check signals</b>, confirm wiring and enable Temperature first. Select <b>Sensors</b> as the reading source and choose your station in the top bar. Fresh measurements arrive about every five seconds; those over 30 seconds old are delayed.')
p('<b>Phone:</b> on the laptop open <b>Settings &gt; Create pairing code</b>. Open <b>http://LAPTOP_IP:8501</b> on the phone and enter its eight-digit code within five minutes. It is single use and grants full app access, including calibration and shared chats. Pair only trusted devices. Pairing does not encrypt Wi-Fi traffic.','small')
footer()

header('3 / Calibrate pH and cloudiness', 'Enable each sensor only after its wiring and protected signal have been checked.')
heading('pH / SEN0161-V2')
p('<b>1.</b> In Sensor setup, enable pH after its wiring check. Open the pH calibration section. The raw signal is <b>ph_mv</b>, measured at the actual ESP32 input; pH stays missing until calibrated.')
p('<b>2.</b> Use two certified buffers that bracket the expected samples. Rinse between buffers, follow the probe/buffer handling instructions and let the reading stabilize. Note each buffer pH at its actual temperature and several stable ph_mv samples. Do not reuse contaminated buffer.')
table([['Calibration worksheet','Your measured values'],['A: buffer pH / input mV','____________ / ____________'],['B: buffer pH / input mV','____________ / ____________'],['Temperature / date / operator','____________ / ____________ / ____________']],[180,343])
p('<b>3.</b> In <b>Sensors &gt; Calibrate</b>, confirm that the probe has settled, then select Capture reference for each buffer (or enter measured mV manually). Enter each buffer pH. Labels are not calibration values. Choose a span covering the water: a 4-to-7 calibration does not cover pH 7.2.')
p('<b>4.</b> Save pH calibration and wait for Settings acknowledged. Recheck both buffers and an independent reference. The receiver interpolates only inside the saved span; no firmware upload is needed. Temperature compensation and manufacturer accuracy have not been validated for this implementation.')
heading('Cloudiness / SEN0189')
p('<b>1.</b> Confirm analog mode and the divider, then enable Cloudiness in Sensor setup. Read <b>raw.turbidity_mv</b> at GPIO35 after the divider. Raw ADC counts are not NTU.')
p('<b>2.</b> Use at least two certified turbidity standards spanning the intended range. Follow their handling instructions; keep sensor placement consistent and remove bubbles. Record stable input mV for each known NTU standard. Tap water or arbitrary muddy water is not an NTU standard.')
p('<b>3.</b> Choose 2-5 standards in the Cloudiness section. Capture or enter each input mV with its matching standard NTU. The app sorts pairs by increasing mV; NTU may decrease as voltage rises. Use actual measurements, never guessed example numbers.')
p('<b>4.</b> Save cloudiness calibration and wait for Settings acknowledged. Test the standards again. Settings are versioned and apply to new samples; old history stays unchanged. NTU is missing outside the measured span. If standards are unavailable, keep raw-only operation.')
footer()

header('4 / Check temperature and water level', 'Distance to the water surface and water height are different measurements.')
heading('Temperature / DS18B20')
p('Enable Temperature in Sensor setup. Compare with a reference thermometer after both stabilize in the same water. Capture the probe reading, enter the reference reading and Save temperature correction. Correction is limited to +/-5 degrees; investigate larger differences. Recheck at another relevant temperature. Raw readings remain unchanged. No response can mean wiring, missing 4.7k pullup, cable/power trouble or a faulty probe.')
heading('Water level / JSN-SR04T')
p('<b>1.</b> Confirm the exact JSN revision, trigger/echo mode, supply, input requirements and distance range. Fit the ECHO divider before connecting GPIO18. Enable Water level in Sensor setup. Compare raw.distance_cm with a ruler using a stable target outside the blind zone.')
p('<b>2.</b> Mount the transducer above the water, pointing down. At your chosen zero level, capture or enter Distance to zero level in the app. Enter verified minimum and maximum distances for your actual revision, not an internet value for a similar module.')
# Compact geometry illustration.
global_y=y
c.setStrokeColor(PURPLE);c.setLineWidth(1.5)
c.roundRect(56,y-40,106,28,6,stroke=1,fill=0);c.setFont('Helvetica-Bold',10);c.setFillColor(INK);c.drawString(68,y-30,'Transducer face')
c.line(109,y-40,109,y-135);c.setStrokeColor(GREEN);c.line(58,y-90,235,y-90);c.setStrokeColor(LINE);c.line(58,y-135,235,y-135)
c.setFont('Helvetica',10);c.drawString(245,y-91,'Water surface: measured distance down from face')
c.drawString(245,y-135,'Chosen zero-height plane: reference distance')
c.setFillColor(PURPLE);c.drawString(56,y-158,'Water height = reference distance - measured distance')
y-=178
p('<b>Example geometry only:</b> reference 60 cm and measured distance 45 cm means 15 cm water height. These are not settings for your tank. Keep the highest water surface comfortably outside the verified minimum range; do not mount inside the blind zone.')
p('<b>3.</b> Save water-level calibration and wait for Settings acknowledged. Check two or more known water heights with a ruler. Timeouts, blind-zone echoes, out-of-range echoes and negative heights stay missing; nothing is replaced with a fake zero.')
heading('Mark the installed station as verified')
p('After physically checking all four enabled, calibrated sensors, use Save verification in Sensor setup. Each revision gets an ID (app-r1, app-r2, etc.); download saved settings for your notes. Any setting change clears verification. A packet is marked calibrated only when verification is declared and all four values are available. Partial stations remain provisional.')
footer()

header('5 / Read the dashboard and fix problems', 'The first goal: real, traceable measurements - not four filled-in numbers.')
heading('What success looks like')
p('Select Sensors as the reading source and the correct station. Transmission and measurement times should update; temperature should respond to a real change. Missing pH/NTU or water level is normal before calibration. Sensors shows raw signals and calibration revision. Open History &amp; reports for the complete readings CSV and observation report. The CSV separates raw values and includes the applied threshold settings.')
table([['What you see','What to check'],['Waiting for Wi-Fi','SSID/password, 2.4 GHz, signal and network availability.'],['Waiting for NTP clock','Internet or a trusted LAN time server is required; no fake timestamps are sent.'],['No 201 / HTTP negative code','Receiver running, correct laptop IPv4/port 8000, private firewall and Wi-Fi isolation.'],['HTTP 401 / 403','Missing, mismatched or revoked API_TOKEN. Restore the matching private station_config.h; a replacement credential needs a new upload.'],['HTTP 422','Field names, units, sensor range and station clock. More than 5 seconds ahead is rejected.'],['Needs calibration','Enter measured references in Sensors > Calibrate. No routine reflash is needed.'],['Check analog input','Power off; check divider, ground, ADC wiring and voltage. Never bypass the divider.'],['No echo / outside sensor range','JSN mode, trigger compatibility, ECHO divider, mounting, range and target.'],['Upload cannot find board','USB data cable, COM port and board driver. Close Serial Monitor.'],['Delayed / wrong clock','Reconnect or resync. Retries do not make an old measurement fresh.']],[140,383])
p('Prototype reference bands and the synthetic-trained anomaly model are not water-safety tests, confirmed pollution, official WQI or validated flood predictions. Calibration is an operator check, not automatic certification. TDS remains optional and unimplemented until its model is confirmed.','small')
heading('Verified references / check your exact module')
for label,url in [
 ('DFRobot pH V2: supply, output and calibration','https://wiki.dfrobot.com/sen0161-v2/'),
 ('DFRobot turbidity: 5 V supply, 0-4.5 V output','https://wiki.dfrobot.com/sen0189'),
 ('Analog Devices: DS18B20 pullup','https://support.analog.com/en-US/knowledgebase/article/000094969'),
 ('Espressif: GPIO limits and strapping','https://documentation.espressif.com/esp32_datasheet_en.html'),
 ('PlatformIO build / upload','https://docs.platformio.org/en/latest/core/userguide/cmd_run.html')]:
 p(f'<link href="{url}" color="#6553ad">{escape(label)}</link>','small',4)
p('JSN revision and USB-C power circuitry remain unconfirmed; check the supplied documentation. Remote-v1 firmware compiled successfully. Enable states persist on the board; versioned calibration settings live on the laptop. Physical hardware remains untested.','small')
footer()

header('6 / Tank, stand and sensor layout','Illustrative side view - not to scale. Size the stand from the verified JSN range.',True)
t=Drawing(770,425)
def tt(x,y,text,size=10,color=INK,bold=False): t.add(String(x,y,text,fontName='Helvetica-Bold' if bold else 'Helvetica',fontSize=size,fillColor=color))
def tl(x1,y1,x2,y2,color=INK,width=1.5,dash=None): t.add(Line(x1,y1,x2,y2,strokeColor=color,strokeWidth=width,strokeDashArray=dash))
tt(225,402,'H >= W + B + M',15,PURPLE,True)
tt(225,384,'B = actual minimum distance; M = added mounting margin',10,MUTED)
tl(18,65,744,65,INK,3);tt(22,45,'Level, load-rated table / spill tray',10)
tl(110,65,110,375,INK,9);tl(110,375,445,375,INK,7)
tl(55,65,110,115,INK,3);tl(165,65,110,115,INK,3)
tt(10,190,'Separate',10);tt(10,176,'secured stand',10);tt(10,162,'Two clamps',10)
t.add(Rect(25,288,172,78,rx=10,ry=10,fillColor=PALE,strokeColor=LINE))
tt(37,344,'Dry electronics box',12,INK,True);tt(37,326,'ESP32 + interface boards',10);tt(37,309,'above fill / splash zone',10)
t.add(Rect(239,76,382,207,fillColor=None,strokeColor=INK,strokeWidth=2))
t.add(Rect(242,79,376,133,fillColor=colors.HexColor('#d8eeec'),strokeColor=None))
tl(242,212,618,212,GREEN,2);tl(242,235,618,235,RED,1.2,[5,4])
tt(245,242,'Marked maximum fill line',9,RED)
tt(245,84,'Chosen zero-height plane',9,MUTED)
t.add(Rect(421,350,38,22,rx=4,ry=4,fillColor=PALE,strokeColor=PURPLE,strokeWidth=1.5))
tt(472,356,'JSN face points down',10,PURPLE,True)
tl(440,350,396,212,PURPLE,1,[5,4]);tl(440,350,484,212,PURPLE,1,[5,4])
tt(362,296,'Keep the beam clear',10,PURPLE)
tl(197,323,208,323,PURPLE);tl(208,323,208,270,PURPLE);tl(208,270,225,270,PURPLE);tl(225,270,225,300,PURPLE);tl(225,300,300,300,PURPLE)
tt(8,264,'Cable glands',9);tt(8,250,'Drip loops',9);tt(8,236,'below entries',9)
tl(285,283,285,181,PURPLE,2);t.add(Rect(279,126,12,55,rx=4,ry=4,fillColor=colors.white,strokeColor=PURPLE))
tl(342,283,342,176,PURPLE,2);t.add(Rect(337,138,10,38,rx=3,ry=3,fillColor=colors.white,strokeColor=PURPLE))
tt(250,112,'pH tip',9);tt(322,122,'DS18B20',9)
tl(525,283,525,278,PURPLE,2);t.add(Rect(511,245,28,33,rx=4,ry=4,fillColor=PALE,strokeColor=PURPLE))
t.add(Rect(517,209,16,36,fillColor=colors.white,strokeColor=PURPLE))
tt(390,170,'SEN0189: permitted',8.5);tt(390,156,'sensing section only',8.5);tt(500,310,'Upper body dry',9)
tl(525,209,525,184,MUTED,1);tl(525,184,482,184,MUTED,1)
tl(440,372,440,375,PURPLE);tl(440,375,197,375,PURPLE);tl(197,375,197,350,PURPLE)
for xx,low,high in [(655,79,350),(638,79,235)]:
 tl(xx,low,xx,high,PURPLE,1);tl(xx-4,low,xx+4,low,PURPLE);tl(xx-4,high,xx+4,high,PURPLE)
tt(670,320,'H: face to zero',9,PURPLE);tt(670,180,'W: max water',9,PURPLE);tt(670,166,'height',9,PURPLE)
tt(225,18,'Tank carries no stand or enclosure load. Mains adapters and laptop stay away from spills.',9,INK,True)
renderPDF.draw(t,c,36,57)
if '--pdf-only' not in sys.argv:
 renderSVG.drawToFile(t,str(ROOT/'Tank-Layout.svg'))
footer()

header('7 / Build and commission the tank','Based on your supplied assembly notes, reconciled with this firmware and wiring.')
heading('1. Dry-table test before construction')
p('Get one real DS18B20 reading into Sensor setup first. Prepare a ready-made transparent tank, level support/spill tray, PVC pole/cross-arm, braced stand and clamps, removable probe hangers, splash-resistant enclosure, glands, ties, ruler and jug. Have an experienced person cut/drill the enclosure with electronics removed. Do not drill a glass tank.')
heading('2. Measure the clearance, then build the stand')
p('Confirm the exact JSN revision and distance range. Choose the highest water level W and extra margin M; set face-to-zero height H >= W + verified minimum distance B + M. Also keep the lowest water within maximum sensor range. Example only: W=20 cm, B=25 cm, M=5 cm requires H >= 50 cm. Do not copy these values into the app.')
p('Fix the pole to its own stable frame/table mount with two spaced clamps and a secured, braced base. The tank rim must not support the electronics weight. Temporarily hold the JSN over the proposed position and test known distances before permanently fixing the arm. Avoid walls, braces and other probes in its beam.')
heading('3. Leak-test, hang the probes and secure cables')
p('Leak-test on the final flat, load-rated support with electronics removed. Fill gradually; one litre of water is roughly one kilogram. Mark a maximum fill line that preserves JSN clearance. Lower/empty the water before working on mounts.')
p('Keep the pH tip and waterproof temperature probe at repeatable supplier-approved depths, clear of the bottom and each other. Do not clamp glass tips. Immerse only the allowed SEN0189 sensing section; keep its upper body and connector dry. The JSN stays above water and points down. Keep every interface/controller board dry in the elevated enclosure; add glands, strain relief and drip loops. Do not cut probe cables or assume a box with an open USB entry is weatherproof.')
heading('4. Recheck the installed station in the app')
p('Use separate 10k/15k dividers for turbidity and ECHO; the attached notes\' 10k/20k alternative is not used here. Verify all grounds and the protected inputs before power. Enable each channel only after its wiring check. Use Sensor setup for calibration; moving the arm or zero plane requires new water-level calibration.')
p('Fill in controlled stages below the marked limit. Check at least two ruler-measured water heights and recheck pH/NTU/temperature references after mounting. Save verification, then download station settings, CSV and an observation report. Photograph the final cable routing and keep a calibration log.')
heading('5. Demonstrate and pack away')
p('Clean soil in a separate water sample can illustrate a relative cloudiness response, not known NTU or confirmed pollution. Keep buffers in separate labelled containers. Do not add unknown chemicals, detergent, fish or wastewater. Disconnect low-voltage power before moving probes; empty safely and store each probe as its supplier directs. Keep mains adapters and the laptop away from spills.')
footer()
c.save()
print(pdf)

