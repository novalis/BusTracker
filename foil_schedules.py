from email.MIMEText import MIMEText
from mechanize import Browser

import datetime
import smtplib

email_address = "novalis@openplans.org"

def send_mail(subject, body):
    # Set up a MIMEText object (it's a dictionary)
    msg = MIMEText(body)  

    msg['Subject'] = subject
    msg['From'] = email_address
    msg['To'] = to

    s = smtplib.SMTP()
    s.connect("localhost")
    s.sendmail(email_address, email_address, msg.as_string())
    s.close()

urls = {'mtahq' : 'http://mta-nyc2.custhelp.com/cgi-bin/mta_nyc2.cfg/php/enduser/ask.php?p_prod_lvl1=70&p_prod_lvl2=71&p_cat_lvl1=35'}

prod_lvl_2 = {'nyct' : '72',
              'mta_bus' : '78',
              'mtaqh' : '71',
              }

form1 = dict(
    p_userid=email_address,
    p_icf_183='David Turner',
    p_icf_184='The Open Planning Project',
    p_icf_185='349 W 12th St #3',
    p_icf_191='New York, NY 10014',
    p_icf_186='617-441-0668',
    p_subject='Bus and Subway schedules',
    p_question="""

Dear MTA,

Please send me all current and future schedule and route information
for all buses and/or subways, including the dates that each schedule
and/or route becomes active and inactive.  I will be sending one copy
of this request every day, because I can see no other way to get
up-to-date data.  Since I have been told that it takes 30 days to get
a reply, I expect to receive one CD every day (after an initial 30 day
delay).  Of course, if it is possible to get data sooner than 30 days,
that would be even better.

If, when you are generating a CD, the schedule and route data have not
changed since you previously generated a CD for me, there's no need to
resend the data.  Just send me an email telling me that the data has
not been updated.

If possible, I would prefer to download the data via HTTP or FTP
rather than getting a CD in the mail.

"""
)

br = Browser()
br.set_handle_robots(False)
today = str(datetime.date.today())

for agency, url in urls.items():

    br.open(url)
    br.select_form(name="_main")

    for k, v in form1.items():
        br[k] = v

    #this is done with JS so we must simulate it manually.
    #this is horrible, but the JS is evil, so...
    value = prod_lvl_2[agency]
    br.form.find_control('p_prod_lvl2').items[-1].__dict__['value'] = value
    br.form.find_control('p_prod_lvl2').items[-1].__dict__['label'] = value
    br.form.find_control('p_prod_lvl2').items[-1].__dict__['name'] = value
    br['p_prod_lvl2'] = [value]     

    response2 = br.submit()
    success = response2.read()

    f = open('%s_%s_response2.html' % (agency, today), "w")
    f.write(success)
    f.close()

    if not 'The reference number' in success:
        send_mail('Failed MTA request for %s' % agency, 
"""
We couldn't send a FOIL request to the MTA. The details are in 
%s_%s_response2.html
""" % (agency, today))



