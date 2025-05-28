                                    Why I started this project

New to coding and starting a computer games programming course this september, I work at a local pub 
and they use a physical a4 spreadsheet which is used to display the sign IN/OUT times of every employee
for the days they work that week. Once I got an offer from the UNI I wanted to start at I figured a
good idea to learn coding would be to make something that could be useful in life, so I made code 
using pyhton and aws textract to calculate the total hours for each perosn just by taking a photo.

                                What the project actually is/does
It takes the photo you provide (Has to be well lit, and I crop the image so it's just the spreadsheet)
and it then shows total hours it thinks each person has worked, you can decide to make edit whatever
time is either incorrect, if they signed out early from 10-12 because I made it so it recognises that
as 10am-11pm because the pub I work at opens at 10 only, also no one works for 2 hours, so I concluded
they have to be sick and that's what the edit in the terminal is for, then once you type "done" it will
show the finalised hours for each person.

                                       Overall thoughts
At the stage the code is in it's honestly reliable but not 100%, it works for my specific spreadsheet
I personally made, and iv'e ran multiple scans using my actual work spreadsheets and fixed some bugs such as
the IN/OUT time numbers such as 7 being read as > from the textract and also 10:30 being read as i0/3o
but iv'e decided to stop working on this project as with my current knowledge and time I don't think it's
worth it when I can use the time to learn code in a better way.
