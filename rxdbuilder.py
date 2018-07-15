# Example of embedding CEF Python browser using wxPython library.
# This example has a top menu and a browser widget without navigation bar.

# Tested configurations:
# - wxPython 4.0 on Windows/Mac/Linux
# - wxPython 3.0 on Windows/Mac
# - wxPython 2.8 on Linux
# - CEF Python v55.4+

import wx
from cefpython3 import cefpython as cef
import platform
import sys
import os
import base64
import json

# Fix for PyCharm hints warnings when using static methods
WindowUtils = cef.WindowUtils()

# Platforms
WINDOWS = (platform.system() == "Windows")
LINUX = (platform.system() == "Linux")
MAC = (platform.system() == "Darwin")

# Configuration
WIDTH = 800
HEIGHT = 600

# Globals
g_count_windows = 0


def main():
    check_versions()
    sys.excepthook = cef.ExceptHook  # To shutdown all CEF processes on error
    settings = {}
    if WINDOWS:
        # noinspection PyUnresolvedReferences, PyArgumentList
        cef.DpiAware.EnableHighDpiSupport()
    cef.Initialize(settings=settings)
    app = CefApp(False)
    app.MainLoop()
    del app  # Must destroy before calling Shutdown
    if not MAC:
        # On Mac shutdown is called in OnClose
        cef.Shutdown()


def check_versions():
    """print("[wxpython.py] CEF Python {ver}".format(ver=cef.__version__))
    print("[wxpython.py] Python {ver} {arch}".format(
            ver=platform.python_version(), arch=platform.architecture()[0]))
    print("[wxpython.py] wxPython {ver}".format(ver=wx.version()))"""
    # CEF Python version requirement
    assert cef.__version__ >= "55.3", "CEF Python v55.3+ required to run this"

with open('rxdbuilder.html') as f:
    my_html = f.read()


def html_to_data_uri(html, js_callback=None):
    # This function is called in two ways:
    # 1. From Python: in this case value is returned
    # 2. From Javascript: in this case value cannot be returned because
    #    inter-process messaging is asynchronous, so must return value
    #    by calling js_callback.
    html = html.encode("utf-8", "replace")
    b64 = base64.b64encode(html).decode("utf-8", "replace")
    ret = "data:text/html;base64,{data}".format(data=b64)
    if js_callback:
        js_print(js_callback.GetFrame().GetBrowser(),
                 "Python", "html_to_data_uri",
                 "Called from Javascript. Will call Javascript callback now.")
        js_callback.Call(ret)
    else:
        return ret

class MainFrame(wx.Frame):

    def __init__(self):
        wx.Frame.__init__(self, parent=None, id=wx.ID_ANY,
                          title='RxDBuilder', size=(WIDTH, HEIGHT))
        self.browser = None
        self._active_regions = []
        self._active_species = []
        self._active_reactions = []

        # Must ignore X11 errors like 'BadWindow' and others by
        # installing X11 error handlers. This must be done after
        # wx was intialized.
        if LINUX:
            WindowUtils.InstallX11ErrorHandlers()

        global g_count_windows
        g_count_windows += 1

        self.setup_icon()
        self.create_menu()
        self.Bind(wx.EVT_CLOSE, self.OnClose)

        # Set wx.WANTS_CHARS style for the keyboard to work.
        # This style also needs to be set for all parent controls.
        self.browser_panel = wx.Panel(self, style=wx.WANTS_CHARS)
        self.browser_panel.Bind(wx.EVT_SET_FOCUS, self.OnSetFocus)
        self.browser_panel.Bind(wx.EVT_SIZE, self.OnSize)

        if MAC:
            try:
                # noinspection PyUnresolvedReferences
                from AppKit import NSApp
                # Make the content view for the window have a layer.
                # This will make all sub-views have layers. This is
                # necessary to ensure correct layer ordering of all
                # child views and their layers. This fixes Window
                # glitchiness during initial loading on Mac (Issue #371).
                NSApp.windows()[0].contentView().setWantsLayer_(True)
            except ImportError:
                print("[wxpython.py] Warning: PyObjC package is missing, "
                      "cannot fix Issue #371")
                print("[wxpython.py] To install PyObjC type: "
                      "pip install -U pyobjc")

        if LINUX:
            # On Linux must show before embedding browser, so that handle
            # is available (Issue #347).
            self.Show()
            # In wxPython 3.0 and wxPython 4.0 on Linux handle is
            # still not yet available, so must delay embedding browser
            # (Issue #349).
            if wx.version().startswith("3.") or wx.version().startswith("4."):
                wx.CallLater(100, self.embed_browser)
            else:
                # This works fine in wxPython 2.8 on Linux
                self.embed_browser()
        else:
            self.embed_browser()
            self.Show()

    def setup_icon(self):
        icon_file = os.path.join(os.path.abspath(os.path.dirname(__file__)),
                                 "resources", "wxpython.png")
        # wx.IconFromBitmap is not available on Linux in wxPython 3.0/4.0
        if os.path.exists(icon_file) and hasattr(wx, "IconFromBitmap"):
            icon = wx.IconFromBitmap(wx.Bitmap(icon_file, wx.BITMAP_TYPE_PNG))
            self.SetIcon(icon)

    def save_model(self, event):
        with wx.FileDialog(self, "Save RxDBuilder as JSON", wildcard="JSON files (*.json)|*.json",
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as fileDialog:

            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return

            pathname = fileDialog.GetPath()
            try:
                with open(pathname, 'w') as f:
                    f.write(json.dumps({
                            'regions': self._active_regions,
                            'species': self._active_species,
                            'reactions': self._active_reactions
                        }, indent=4))
            except IOError:
                print('Save failed.')
            except:
                print('Mysterious save failure.')

    def save_model_as_python(self, event):
        with wx.FileDialog(self, "Save RxDBuilder as Python", wildcard="Python files (*.py)|*.py",
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as fileDialog:

            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return

            pathname = fileDialog.GetPath()
            try:
                with open(pathname, 'w') as f:
                    f.write(model_to_python(self._active_regions, self._active_species, self._active_reactions))
            except IOError:
                print('Save failed.')
            except:
                print('Mysterious save failure.')

    def instantiate(self, event):
        my_code = model_to_python(self._active_regions, self._active_species, self._active_reactions)
        print('Running:\n' + my_code)
        exec(my_code)

    def create_menu(self):
        filemenu = wx.Menu()
        m_save = filemenu.Append(1, "&Save model")
        self.Bind(wx.EVT_MENU, self.save_model, m_save)
        filemenu.Append(2, "Open model").Enable(False)
        filemenu.Append(3, "Import model from NEURON").Enable(False)
        m_export_python = filemenu.Append(4, "Export to Python")
        self.Bind(wx.EVT_MENU, self.save_model_as_python, m_export_python)
        filemenu.Append(5, "Export to SBML").Enable(False)
        filemenu.Append(6, "Import SBML").Enable(False)
        filemenu.AppendSeparator()
        filemenu.Append(7, "Exit").Enable(False)
        menubar = wx.MenuBar()
        menubar.Append(filemenu, "&File")
        instantiatemenu = wx.Menu()
        m_instantiate = instantiatemenu.Append(8, 'Instantiate')
        self.Bind(wx.EVT_MENU, self.instantiate, m_instantiate)
        menubar.Append(instantiatemenu, '&Instantiate')
        self.SetMenuBar(menubar)

    def embed_browser(self):
        window_info = cef.WindowInfo()
        (width, height) = self.browser_panel.GetClientSize().Get()
        assert self.browser_panel.GetHandle(), "Window handle not available yet"
        window_info.SetAsChild(self.browser_panel.GetHandle(),
                               [0, 0, width, height])
        self.browser = cef.CreateBrowserSync(window_info,
                                             url=html_to_data_uri(my_html))
        self.set_browser_callbacks()
        self.browser.SetClientHandler(FocusHandler())

    def set_browser_callbacks(self):
        self.bindings = cef.JavascriptBindings(
            bindToFrames=False, bindToPopups=False)
        self.bindings.SetFunction("_update_data", self._update_data)
        self.browser.SetJavascriptBindings(self.bindings)

    def _update_data(self, var, value):
        if var == 'active_regions':
            self._active_regions = value
        elif var == 'active_species':
            self._active_species = value
        elif var == 'active_reactions':
            self._active_reactions = value
        else:
            print('unknown data type:', var)

    def OnSetFocus(self, _):
        if not self.browser:
            return
        if WINDOWS:
            WindowUtils.OnSetFocus(self.browser_panel.GetHandle(),
                                   0, 0, 0)
        self.browser.SetFocus(True)

    def OnSize(self, _):
        if not self.browser:
            return
        if WINDOWS:
            WindowUtils.OnSize(self.browser_panel.GetHandle(),
                               0, 0, 0)
        elif LINUX:
            (x, y) = (0, 0)
            (width, height) = self.browser_panel.GetSize().Get()
            self.browser.SetBounds(x, y, width, height)
        self.browser.NotifyMoveOrResizeStarted()

    def OnClose(self, event):
        #print("[wxpython.py] OnClose called")
        if not self.browser:
            # May already be closing, may be called multiple times on Mac
            return

        if MAC:
            # On Mac things work differently, other steps are required
            self.browser.CloseBrowser()
            self.clear_browser_references()
            self.Destroy()
            global g_count_windows
            g_count_windows -= 1
            if g_count_windows == 0:
                cef.Shutdown()
                wx.GetApp().ExitMainLoop()
                # Call _exit otherwise app exits with code 255 (Issue #162).
                # noinspection PyProtectedMember
                os._exit(0)
        else:
            # Calling browser.CloseBrowser() and/or self.Destroy()
            # in OnClose may cause app crash on some paltforms in
            # some use cases, details in Issue #107.
            self.browser.ParentWindowWillClose()
            event.Skip()
            self.clear_browser_references()

    def clear_browser_references(self):
        # Clear browser references that you keep anywhere in your
        # code. All references must be cleared for CEF to shutdown cleanly.
        self.browser = None


class FocusHandler(object):
    def OnGotFocus(self, browser, **_):
        # Temporary fix for focus issues on Linux (Issue #284).
        if LINUX:
            print("[wxpython.py] FocusHandler.OnGotFocus:"
                  " keyboard focus fix (Issue #284)")
            browser.SetFocus(True)


class CefApp(wx.App):

    def __init__(self, redirect):
        self.timer = None
        self.timer_id = 1
        self.is_initialized = False
        super(CefApp, self).__init__(redirect=redirect)

    def OnPreInit(self):
        super(CefApp, self).OnPreInit()
        # On Mac with wxPython 4.0 the OnInit() event never gets
        # called. Doing wx window creation in OnPreInit() seems to
        # resolve the problem (Issue #350).
        if MAC and wx.version().startswith("4."):
            print("[wxpython.py] OnPreInit: initialize here"
                  " (wxPython 4.0 fix)")
            self.initialize()

    def OnInit(self):
        self.initialize()
        return True

    def initialize(self):
        if self.is_initialized:
            return
        self.is_initialized = True
        self.create_timer()
        frame = MainFrame()
        self.SetTopWindow(frame)
        frame.Show()

    def create_timer(self):
        # See also "Making a render loop":
        # http://wiki.wxwidgets.org/Making_a_render_loop
        # Another way would be to use EVT_IDLE in MainFrame.
        self.timer = wx.Timer(self, self.timer_id)
        self.Bind(wx.EVT_TIMER, self.on_timer, self.timer)
        self.timer.Start(10)  # 10ms timer

    def on_timer(self, _):
        cef.MessageLoopWork()

    def OnExit(self):
        self.timer.Stop()
        return 0

def model_to_python(regions, species, reactions):
    result = '''from neuron import crxd as rxd
from neuron import h
'''

    active_regions = set()
    for sp in species:
        for r in sp['regions']:
            active_regions.add(r['uuid'])

    region_uuid_lookup = {r['uuid']: r['name'] for r in regions}
    species_uuid_lookup = {r['uuid']: r['name'] for r in species}


    for r in regions:
        if r['uuid'] in active_regions:
            if r['type'] == 'cyt':
                result += '{name} = rxd.Region(h.allsec(), nrn_region="i", name="{name}", geometry=rxd.FractionalVolume(volume_fraction={volumefraction}, neighbor_areas_fraction={volumefraction}, surface_fraction=1))\n'.format(**r)
            elif r['type'] == 'extracellular':
                result += '{name} = rxd.Extracellular(xlo=-500, ylo=-500, xhi=500, yhi=500, zlo=-500, zhi=500, dx={dx}, name="{name}", volume_fraction={volumefraction}, tortuosity={tortuosity})\n'.format(**r)
            else:
                result += '{name} = rxd.Region(h.allsec(), name="{name}", geometry=rxd.FractionalVolume(volume_fraction={volumefraction}, neighbor_areas_fraction={volumefraction}, surface_fraction=0))\n'.format(**r)

    for sp in species:
        if sp['regions']:
            if len(sp['regions']) > 1:
                print('warning: currently ignoring non-uniform d, initial and just using the first value')
            d = sp['regions'][0]['d']
            initial = sp['regions'][0]['initial']
            sp_copy = dict(sp)
            sp_copy['my_regions'] = '[' + ','.join(region_uuid_lookup[r['uuid']] for r in sp['regions']) + ']'
            sp_copy['d'] = d
            sp_copy['initial'] = initial
            result += '{name} = rxd.Species({my_regions}, charge={charge}, name="{name}", d={d}, initial={initial})\n'.format(**sp_copy)
            for r in sp['regions']:
                if r['rate']:
                    data = {
                        'my_region':region_uuid_lookup[r['uuid']],
                        'name': sp['name'],
                        'rate': r['rate']
                    }
                    result += '{name}_{my_region}_rate = rxd.Rate({name}[{my_region}], {rate})\n'.format(**data)

    for r in reactions:
        r['custom_dynamics'] = not(r['mass_action'])
        if r['states']:
            print('Warning: reaction states currently ignored')
        if r['all_regions']:
            reactants = '+'.join('{}*{}'.format(s['stoichiometry'], species_uuid_lookup[s['uuid']]) for s in r['sources'])
            products = '+'.join('{}*{}'.format(s['stoichiometry'], species_uuid_lookup[s['uuid']]) for s in r['dests'])
            data = {
                'custom_dynamics': not(r['mass_action']),
                'reactants': reactants,
                'products': products,
                'name': r['name'],
                'kf': r['kf'],
                'kb': r['kb']
            }
            result += '{name} = rxd.Reaction({reactants}, {products}, {kf}, {kb}, custom_dynamics={custom_dynamics})\n'.format(**data)
        else:
            # check to see if multi-compartment or regular
            involved_regions = set()
            for s in r['sources']:
                involved_regions.add(s['region'])
            for s in r['dests']:
                involved_regions.add(s['region'])
            if len(involved_regions) > 1:
                # multicompartment reaction
                print('warning: multicompartment reactions currently unsupported')
            else:
                # single specific compartment reaction
                reactants = '+'.join('{}*{}'.format(s['stoichiometry'], species_uuid_lookup[s['uuid']]) for s in r['sources'])
                products = '+'.join('{}*{}'.format(s['stoichiometry'], species_uuid_lookup[s['uuid']]) for s in r['dests'])
                data = {
                    'custom_dynamics': not(r['mass_action']),
                    'reactants': reactants,
                    'products': products,
                    'name': r['name'],
                    'kf': r['kf'],
                    'kb': r['kb'],
                    'region': region_uuid_lookup[s['region']]
                }
                result += '{name} = rxd.Reaction({reactants}, {products}, {kf}, {kb}, custom_dynamics={custom_dynamics}, regions=[{region}])\n'.format(**data)

    return result

if __name__ == '__main__':
    main()