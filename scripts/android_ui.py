"""Small UIAutomator helper shared by software-only demo checks. Never selects a physical device implicitly."""
import uiautomator2 as u2
import time

class AndroidUI:
    def __init__(self,serial):
        self.device=u2.connect(serial)
        self.device.settings['wait_timeout']=10
        self.device.jsonrpc.setConfigurator({'waitForIdleTimeout':100,'waitForSelectorTimeout':1000})
    def top(self):
        self.device.shell('cmd statusbar collapse')
        for _ in range(3): self.device.swipe(.5,.3,.5,.85,.15)
    def click(self,text):
        d=self.device
        if not d(text=text).wait(timeout=2):
            self.top()
            for _ in range(10):
                if d(text=text).exists: break
                d.swipe(.5,.85,.5,.3,.15)
        assert d(text=text).wait(timeout=2), f'Missing Android control: {text}'
        d(text=text).click()
    def expect(self,text,timeout=15):
        self.top()
        assert self.device(textContains=text).wait(timeout=timeout),f'Missing Android result: {text}'
    def login(self,data,user):
        d=self.device
        d.shell('input keyevent KEYCODE_WAKEUP');d.shell('wm dismiss-keyguard')
        d.app_start('org.spatial.annotations',activity='.MainActivity',stop=True)
        assert d(text='Spatial Notes').wait(timeout=15)
        d(className='android.widget.EditText')[0].set_text(data['backend'])
        self.click('SAVE SERVER')
        d(text='Username').set_text(user['username'])
        d(text='Password (at least 10 characters)').set_text(user['password'])
        self.click('SIGN IN');self.expect('Signed in: '+user['username'])
        self.click('SCAN / VIEW ANNOTATIONS')
    def manual(self,marker):
        self.click('MANUAL MARKER · SIMULATION')
        self.device(className='android.widget.EditText').set_text(marker)
        time.sleep(1)
        self.device.xpath('//*[@resource-id="android:id/button1"]').click(timeout=15);self.expect('SIMULATION')
    def screenshot(self,path):
        self.top();self.device.screenshot(str(path))
