// Setup.cs — the MyTranscribe Medical installer and uninstaller (one program).
//
// Built by installer/build_installer.py with Windows' own C# compiler (.NET Framework 4.8,
// C# 5). The app is a zip appended to this program, followed by a 16-byte trailer: the
// zip's offset (Int64) and "MTSETUP1". Windows will not start a program file of 4 GiB or more,
// so a larger installer is this program followed by the name of a data file beside it, the
// name's length (Int64) and "MTSETUPD"; the data file is the zip plus the trailer (offset 0).
//
// Install: for the current Windows account only (no administrator rights), into
// %LOCALAPPDATA%\Programs\MyTranscribe Medical; desktop and Start-menu shortcuts; an entry in
// Settings -> Apps (per-user registry). An update replaces the program files and keeps the
// user's settings, word lists and log (they live in %APPDATA% and %LOCALAPPDATA%\MyTranscribe).
// Uninstall: the same program without the zip, copied into the install folder.
//
// Compiled with GPU_EDITION (build_installer.py --gpu) it is the graphics-card edition: its own
// name, folder, shortcuts and Apps entry, so it installs beside the processor-only edition and
// never updates, replaces or removes it (and the other way round).
//
// An update package (build_info.json "kind": "update") carries only the app's own code (src/):
// it needs an installed copy built with the same Python, replaces src/ (put back if anything
// goes wrong) and leaves Python, the packages, the speech model and the shortcuts as they are.
//
// Switches (for scripted tests and managed installs): /S silent (which accepts the licence terms in
// LICENSE-NOTICE.txt), /D=<folder>, /noshortcuts, /uninstall. Windows 11 only (Requirements).

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Reflection;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Win32;

static class Program
{
#if GPU_EDITION
    public const string AppName = "MyTranscribe Medical (graphics card)";
    public const string RegKey = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\MyTranscribeMedicalGPU";
    public const string Device = "cuda";          // build_info.json "device" of this edition
#else
    public const string AppName = "MyTranscribe Medical";
    public const string RegKey = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\MyTranscribeMedical";
    public const string Device = "cpu";
#endif
    public const string UninstallExe = "Uninstall MyTranscribe.exe";
    public static readonly byte[] Magic = System.Text.Encoding.ASCII.GetBytes("MTSETUP1");
    public static readonly byte[] MagicData = System.Text.Encoding.ASCII.GetBytes("MTSETUPD");

    [STAThread]
    static int Main(string[] args)
    {
        var opts = Options.Parse(args);
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        try
        {
            if (opts.Uninstall)
                return Uninstaller.Run(opts);
            string unsupported = Requirements.Problem();
            if (unsupported != null)
            {
                Ui.Error(unsupported, opts);
                return 3;
            }
            string missing;
            var payload = Payload.Open(Application.ExecutablePath, out missing);
            if (payload == null)
            {
                Ui.Error(missing != null
                    ? "This installer needs the file " + missing + " in the same folder as it. Please put the two " +
                      "files together (download both again if needed), then start it again."
                    : "This copy of the installer is incomplete. Please download it again.", opts);
                return 2;
            }
            if (opts.Silent)
                return Installer.RunSilent(payload, opts);
            Application.Run(new InstallForm(payload, opts));
            return 0;
        }
        catch (Exception ex)
        {
            Ui.Error("Something went wrong: " + ex.Message, opts);
            return 1;
        }
    }

    public static string DefaultFolder()
    {
        return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                            "Programs", AppName);
    }

    public static string InstalledFolder()
    {
        using (var key = Registry.CurrentUser.OpenSubKey(RegKey))
            return key == null ? null : key.GetValue("InstallLocation") as string;
    }
}

class Options
{
    public bool Silent, Uninstall, NoShortcuts;
    public string Folder, From;
    public int Parent;

    public static Options Parse(string[] args)
    {
        var o = new Options();
        foreach (var a in args)
        {
            var l = a.ToLowerInvariant();
            if (l == "/s" || l == "/silent") o.Silent = true;
            else if (l == "/uninstall") o.Uninstall = true;
            else if (l == "/noshortcuts") o.NoShortcuts = true;
            else if (l.StartsWith("/d=")) o.Folder = a.Substring(3).Trim('"');
            else if (l.StartsWith("/from=")) o.From = a.Substring(6).Trim('"');
            else if (l.StartsWith("/parent=")) int.TryParse(a.Substring(8), out o.Parent);
        }
        return o;
    }
}

// %TEMP%\MyTranscribe-setup.log: what happened, for silent installs and for support.
static class Log
{
    public static void Write(string line)
    {
        try
        {
            File.AppendAllText(Path.Combine(Path.GetTempPath(), "MyTranscribe-setup.log"),
                               DateTime.Now.ToString("s") + " " + line + Environment.NewLine);
        }
        catch (Exception) { }
    }
}

// The Windows this program and the app support: Windows 11 (build 22000 or later).
static class Requirements
{
    public const int MinBuild = 22000;

    // Why MyTranscribe cannot be installed on this PC, or null. An unreadable build number is let through.
    public static string Problem()
    {
        int build = 0;
        try
        {
            using (var key = Registry.LocalMachine.OpenSubKey(@"SOFTWARE\Microsoft\Windows NT\CurrentVersion"))
                if (key != null) int.TryParse(key.GetValue("CurrentBuildNumber") as string, out build);
        }
        catch (Exception) { }
        if (build == 0 || build >= MinBuild) return null;
        return Program.AppName + " needs Windows 11. This PC runs an older version of Windows (build " + build +
               "). Support for other versions may come later.";
    }
}

static class Ui
{
    public static readonly Color Back = Color.FromArgb(0xF5, 0xF4, 0xED);
    public static readonly Color Ink = Color.FromArgb(0x1F, 0x1E, 0x1D);
    public static readonly Color Muted = Color.FromArgb(0x5E, 0x5D, 0x59);
    public static readonly Color Accent = Color.FromArgb(0xC9, 0x64, 0x42);
    public static readonly Color Line = Color.FromArgb(0xE3, 0xE1, 0xD7);

    public static void Error(string text, Options o)
    {
        Log.Write(text);
        if (o == null || !o.Silent)
            MessageBox.Show(text, Program.AppName, MessageBoxButtons.OK, MessageBoxIcon.Warning);
        else
            Console.Error.WriteLine(text);
    }

    // The app icon, embedded at full size (the exe's own icon resource gives only 32 px).
    public static Icon AppIcon()
    {
        try
        {
            using (var s = Assembly.GetExecutingAssembly().GetManifestResourceStream("MyTranscribe.ico"))
                if (s != null) return new Icon(s);
        }
        catch (Exception) { }
        return Icon.ExtractAssociatedIcon(Application.ExecutablePath);
    }

    public static Image AppImage()
    {
        try
        {
            using (var s = Assembly.GetExecutingAssembly().GetManifestResourceStream("MyTranscribe.png"))
                if (s != null) return new Bitmap(Image.FromStream(s));
        }
        catch (Exception) { }
        return AppIcon().ToBitmap();
    }

    public static Label Text(string text, float size, bool bold, Color colour)
    {
        return new Label
        {
            Text = text, AutoSize = false, ForeColor = colour, BackColor = Color.Transparent,
            Font = new Font("Segoe UI", size, bold ? FontStyle.Bold : FontStyle.Regular)
        };
    }

    public static Button Button(string text, bool primary)
    {
        var b = new Button
        {
            Text = text, FlatStyle = FlatStyle.Flat, Font = new Font("Segoe UI", 9.5f),
            BackColor = primary ? Accent : Color.White, ForeColor = primary ? Color.White : Ink,
            Size = new Size(120, 34), Cursor = Cursors.Hand,
            AccessibleName = text, AccessibleRole = AccessibleRole.PushButton   // announced as a button
        };
        b.FlatAppearance.BorderColor = primary ? Accent : Color.FromArgb(0xDA, 0xD8, 0xCD);
        if (primary)                     // a flat button keeps its colours when disabled: grey it out
            b.EnabledChanged += (s, e) =>
            {
                b.BackColor = b.FlatAppearance.BorderColor = b.Enabled ? Accent : Color.FromArgb(0xE6, 0xCD, 0xC1);
                b.Cursor = b.Enabled ? Cursors.Hand : Cursors.Default;
            };
        return b;
    }
}

// ── The appended zip ─────────────────────────────────────────────────────────
class Payload
{
    public string Path;                  // the file holding the zip: this program, or the data file beside it
    public long Offset, Length;
    public string Exe;                   // this program
    public long StubLength;              // its length without the payload: the uninstaller
    public string Version = "", Kind = "", Python = "", Device = "";
    public string Notice = "";           // LICENSE-NOTICE.txt: the terms shown before installing
    public long UnpackedBytes;
    public int Files;
    public bool IsUpdate { get { return Kind == "update"; } }

    public static string Field(string json, string name)
    {
        var m = System.Text.RegularExpressions.Regex.Match(json, "\"" + name + "\":\\s*\"([^\"]*)\"");
        return m.Success ? m.Groups[1].Value : "";
    }

    // The 16-byte trailer at the end of a file: (Int64 value, true) if it ends with magic.
    static bool Trailer(Stream f, byte[] magic, out long value)
    {
        value = 0;
        if (f.Length < 32) return false;
        f.Seek(-16, SeekOrigin.End);
        var tail = new byte[16];
        if (f.Read(tail, 0, 16) != 16 || !tail.Skip(8).SequenceEqual(magic)) return false;
        value = BitConverter.ToInt64(tail, 0);
        return true;
    }

    // missing: the data file's name when this program expects one beside it and it is not there.
    public static Payload Open(string exe, out string missing)
    {
        missing = null;
        Payload p;
        using (var f = File.OpenRead(exe))
        {
            long value;
            if (Trailer(f, Program.Magic, out value))
                p = new Payload { Path = exe, Offset = value, Length = f.Length - 16 - value, Exe = exe, StubLength = value };
            else if (Trailer(f, Program.MagicData, out value) && value > 0 && value < 1024)
            {
                var name = new byte[value];
                f.Seek(-16 - value, SeekOrigin.End);
                if (f.Read(name, 0, name.Length) != name.Length) return null;
                string dataName = System.Text.Encoding.UTF8.GetString(name);
                string folder = System.IO.Path.GetDirectoryName(exe);
                string data = System.IO.Path.Combine(folder, dataName);
                if (!File.Exists(data))            // this program renamed (a download's " (1)"): its own name
                    data = System.IO.Path.ChangeExtension(exe, ".data");
                if (!File.Exists(data)) { missing = dataName; return null; }
                using (var d = File.OpenRead(data))
                {
                    long offset;
                    if (!Trailer(d, Program.Magic, out offset)) return null;
                    p = new Payload { Path = data, Offset = offset, Length = d.Length - 16 - offset,
                                      Exe = exe, StubLength = f.Length - 16 - value };
                }
            }
            else return null;
        }
        using (var zip = p.OpenZip())
        {
            foreach (var e in zip.Entries)
            {
                p.UnpackedBytes += e.Length;
                p.Files++;
            }
            var info = zip.GetEntry("build_info.json");
            if (info != null)
                using (var r = new StreamReader(info.Open()))
                {
                    string json = r.ReadToEnd();
                    p.Version = Field(json, "version");
                    p.Kind = Field(json, "kind");
                    p.Python = Field(json, "python");
                    p.Device = Field(json, "device");
                }
            var notice = zip.GetEntry("LICENSE-NOTICE.txt");
            if (notice != null)
                using (var r = new StreamReader(notice.Open()))
                    p.Notice = r.ReadToEnd();
        }
        return p;
    }

    public ZipArchive OpenZip()
    {
        return new ZipArchive(new SliceStream(File.OpenRead(Path), Offset, Length), ZipArchiveMode.Read, false);
    }
}

// A read-only window onto part of a file (the zip inside this program).
class SliceStream : Stream
{
    readonly Stream inner;
    readonly long start, length;
    long pos;

    public SliceStream(Stream inner, long start, long length)
    {
        this.inner = inner; this.start = start; this.length = length;
    }

    public override bool CanRead { get { return true; } }
    public override bool CanSeek { get { return true; } }
    public override bool CanWrite { get { return false; } }
    public override long Length { get { return length; } }
    public override long Position { get { return pos; } set { pos = value; } }
    public override void Flush() { }

    public override int Read(byte[] buffer, int offset, int count)
    {
        long left = length - pos;
        if (left <= 0) return 0;
        if (count > left) count = (int)left;
        inner.Seek(start + pos, SeekOrigin.Begin);
        int n = inner.Read(buffer, offset, count);
        pos += n;
        return n;
    }

    public override long Seek(long offset, SeekOrigin origin)
    {
        if (origin == SeekOrigin.Begin) pos = offset;
        else if (origin == SeekOrigin.Current) pos += offset;
        else pos = length + offset;
        return pos;
    }

    public override void SetLength(long value) { throw new NotSupportedException(); }
    public override void Write(byte[] b, int o, int c) { throw new NotSupportedException(); }

    protected override void Dispose(bool disposing)
    {
        if (disposing) inner.Dispose();
        base.Dispose(disposing);
    }
}

// ── Installing ───────────────────────────────────────────────────────────────
static class Installer
{
    public static int RunSilent(Payload p, Options o)
    {
        try
        {
            if (p.IsUpdate)
            {
                string target = o.Folder ?? Program.InstalledFolder() ?? Program.DefaultFolder();
                Update(p, target, null);
                Log.Write("updated " + target + " to " + p.Version);
                return 0;
            }
            Install(p, o.Folder ?? Program.DefaultFolder(), !o.NoShortcuts, null);
            Log.Write("installed to " + (o.Folder ?? Program.DefaultFolder()));
            return 0;
        }
        catch (Exception ex)
        {
            Log.Write((p.IsUpdate ? "update" : "install") + " failed: " + ex);
            return 1;
        }
    }

    // The build_info.json "device" of the copy installed in folder ("cpu", "any" or "cuda"), or "" if none.
    public static string InstalledDevice(string folder)
    {
        string info = Path.Combine(folder, "build_info.json");
        if (!File.Exists(info)) return "";
        string device = Payload.Field(File.ReadAllText(info), "device");
        return device == "" ? "cpu" : device;
    }

    // Why folder holds the other edition (which this program must leave alone), or null. The
    // processor-only ("cpu") and every-PC ("any") builds are one app and may update each other; the
    // graphics-card edition ("cuda") is kept apart from both.
    public static string OtherEdition(Payload p, string folder)
    {
        string installed = InstalledDevice(folder);
        string mine = p.Device == "" ? Program.Device : p.Device;
        if (installed == "" || (installed == "cuda") == (mine == "cuda")) return null;
        return folder + " holds the " + (installed == "cuda" ? "graphics-card edition" : "standard edition") + " of " +
               "MyTranscribe Medical, which this installer leaves as it is. Please choose another folder.";
    }

    // progress(done bytes, total bytes)
    public static void Install(Payload p, string folder, bool shortcuts, Action<long, long> progress)
    {
        string other = OtherEdition(p, folder);
        if (other != null) throw new InvalidOperationException(other);
        string parent = Path.GetDirectoryName(folder);
        Directory.CreateDirectory(parent);
        string old = folder + ".old";
        if (Directory.Exists(old)) TryDelete(old);

        // An earlier version is set aside first (it is idle, so renaming it is reliable; a copy
        // that is still running keeps its files locked), and put back if anything goes wrong.
        if (Directory.Exists(folder))
        {
            bool moved = false;
            for (int i = 0; i < 4 && !moved; i++)
            {
                try { Directory.Move(folder, old); moved = true; }
                catch (IOException) { Thread.Sleep(500); }
                catch (UnauthorizedAccessException) { Thread.Sleep(500); }
            }
            if (!moved)
                throw new IOException(Program.AppName + " is still running. Close it (the window, and the " +
                                      "icon by the clock if there is one), then try again.");
        }
        try
        {
            Extract(p, folder, progress);
        }
        catch (Exception)
        {
            TryDelete(folder);
            if (Directory.Exists(old) && !Directory.Exists(folder)) Directory.Move(old, folder);
            throw;
        }
        if (Directory.Exists(old)) TryDelete(old);

        if (shortcuts)
        {
            Shortcuts.Create(folder);
        }
        Register(folder, p);
    }

    // Why an update package cannot be applied to folder, or null if it can.
    public static string UpdateProblem(Payload p, string folder)
    {
        if (!File.Exists(Path.Combine(folder, "python", "python.exe")))
            return Program.AppName + " is not installed on this PC. This file only updates an installed copy: " +
                   "install it with the full installer first.";
        string other = OtherEdition(p, folder);
        if (other != null) return other;
        string info = Path.Combine(folder, "build_info.json");
        string installedPython = File.Exists(info) ? Payload.Field(File.ReadAllText(info), "python") : "";
        if (p.Python != "" && installedPython != "" && p.Python != installedPython)
            return "This update does not fit the installed copy (it was built with a different Python). " +
                   "Please use the full installer instead.";
        return null;
    }

    // A copy of the app started from this folder (its Python) is running.
    public static bool Running(string folder)
    {
        string python = Path.GetFullPath(Path.Combine(folder, "python")) + Path.DirectorySeparatorChar;
        foreach (var name in new[] { "python", "pythonw" })
            foreach (var proc in Process.GetProcessesByName(name))
            {
                try
                {
                    if (proc.MainModule.FileName.StartsWith(python, StringComparison.OrdinalIgnoreCase))
                        return true;
                }
                catch (Exception) { }
                finally { proc.Dispose(); }
            }
        return false;
    }

    // An update package: replaces src/ (put back if anything goes wrong) and the small files
    // beside it; Python, the packages, the model and the shortcuts stay as they are.
    public static void Update(Payload p, string folder, Action<long, long> progress)
    {
        string problem = UpdateProblem(p, folder);
        if (problem != null) throw new InvalidOperationException(problem);
        if (Running(folder))
            throw new IOException(Program.AppName + " is still running. Close it (the window, and the " +
                                  "icon by the clock if there is one), then try again.");
        string src = Path.Combine(folder, "src"), old = src + ".old";
        if (Directory.Exists(old)) TryDelete(old);
        for (int i = 0; Directory.Exists(src); i++)
        {
            try { Directory.Move(src, old); }
            catch (IOException) { if (i >= 3) throw; Thread.Sleep(500); }
            catch (UnauthorizedAccessException) { if (i >= 3) throw; Thread.Sleep(500); }
        }
        try
        {
            Extract(p, folder, progress);
        }
        catch (Exception)
        {
            TryDelete(src);
            if (Directory.Exists(old) && !Directory.Exists(src)) Directory.Move(old, src);
            throw;
        }
        TryDelete(old);
        using (var key = Registry.CurrentUser.OpenSubKey(Program.RegKey, true))
            if (key != null) key.SetValue("DisplayVersion", p.Version);
    }

    static void Extract(Payload p, string folder, Action<long, long> progress)
    {
        Directory.CreateDirectory(folder);
        string root = Path.GetFullPath(folder);
        long done = 0;
        var buffer = new byte[1 << 20];
        using (var zip = p.OpenZip())
        {
            foreach (var e in zip.Entries)
            {
                string target = Path.GetFullPath(Path.Combine(folder, e.FullName));
                if (!target.StartsWith(root, StringComparison.OrdinalIgnoreCase))
                    throw new IOException("Unexpected file in the installer: " + e.FullName);
                if (e.FullName.EndsWith("/")) { Directory.CreateDirectory(target); continue; }
                Directory.CreateDirectory(Path.GetDirectoryName(target));
                using (var input = e.Open())
                using (var output = File.Create(target))
                {
                    int n;
                    while ((n = input.Read(buffer, 0, buffer.Length)) > 0)
                    {
                        output.Write(buffer, 0, n);
                        done += n;
                        if (progress != null) progress(done, p.UnpackedBytes);
                    }
                }
            }
        }
        // The uninstaller is this program without the zip.
        using (var self = File.OpenRead(p.Exe))
        using (var un = File.Create(Path.Combine(folder, Program.UninstallExe)))
        {
            long left = p.StubLength;
            int n;
            while (left > 0 && (n = self.Read(buffer, 0, (int)Math.Min(buffer.Length, left))) > 0)
            {
                un.Write(buffer, 0, n);
                left -= n;
            }
        }
    }

    static void Register(string folder, Payload p)
    {
        using (var key = Registry.CurrentUser.CreateSubKey(Program.RegKey))
        {
            key.SetValue("DisplayName", Program.AppName);
            key.SetValue("DisplayVersion", p.Version);
            key.SetValue("Publisher", "MyTranscribe");
            key.SetValue("DisplayIcon", Path.Combine(folder, "src", "assets", "mytranscribe.ico"));
            key.SetValue("InstallLocation", folder);
            key.SetValue("UninstallString", "\"" + Path.Combine(folder, Program.UninstallExe) + "\" /uninstall");
            key.SetValue("QuietUninstallString", "\"" + Path.Combine(folder, Program.UninstallExe) + "\" /uninstall /S");
            key.SetValue("InstallDate", DateTime.Now.ToString("yyyyMMdd"));
            key.SetValue("EstimatedSize", (int)Math.Min(int.MaxValue, p.UnpackedBytes / 1024), RegistryValueKind.DWord);
            key.SetValue("NoModify", 1, RegistryValueKind.DWord);
            key.SetValue("NoRepair", 1, RegistryValueKind.DWord);
        }
    }

    public static void TryDelete(string folder)
    {
        for (int i = 0; i < 10; i++)
        {
            try { if (Directory.Exists(folder)) Directory.Delete(folder, true); return; }
            catch (IOException) { Thread.Sleep(400); }
            catch (UnauthorizedAccessException) { Thread.Sleep(400); }
        }
    }

    public static void Start(string folder)
    {
        var psi = new ProcessStartInfo(Path.Combine(folder, "python", "pythonw.exe"),
                                       "\"" + Path.Combine(folder, "src", "gui_med.py") + "\"")
        {
            WorkingDirectory = folder, UseShellExecute = false
        };
        Process.Start(psi);
    }
}

static class Shortcuts
{
    public static string Desktop() { return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), Program.AppName + ".lnk"); }
    public static string StartMenu() { return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs), Program.AppName + ".lnk"); }

    public static void Create(string folder)
    {
        foreach (var link in new[] { Desktop(), StartMenu() })
            Make(link, folder);
    }

    static void Make(string link, string folder)
    {
        Type t = Type.GetTypeFromProgID("WScript.Shell");
        object shell = Activator.CreateInstance(t);
        object lnk = t.InvokeMember("CreateShortcut", BindingFlags.InvokeMethod, null, shell, new object[] { link });
        Type lt = lnk.GetType();
        Action<string, object> set = (name, value) => lt.InvokeMember(name, BindingFlags.SetProperty, null, lnk, new[] { value });
        set("TargetPath", Path.Combine(folder, "python", "pythonw.exe"));
        set("Arguments", "\"" + Path.Combine(folder, "src", "gui_med.py") + "\"");
        set("WorkingDirectory", folder);
        set("IconLocation", Path.Combine(folder, "src", "assets", "mytranscribe.ico") + ",0");
        set("Description", "Dictation that stays on this PC");
        lt.InvokeMember("Save", BindingFlags.InvokeMethod, null, lnk, null);
    }

    public static void Remove()
    {
        foreach (var link in new[] { Desktop(), StartMenu() })
            if (File.Exists(link)) File.Delete(link);
    }
}

// ── The install window ───────────────────────────────────────────────────────
class InstallForm : Form
{
    readonly Payload payload;
    readonly Options opts;
    readonly string folder;
    readonly Panel body = new Panel();
    readonly Button primary = Ui.Button("Install", true);
    readonly Button secondary = Ui.Button("Cancel", false);
    readonly ProgressBar bar = new ProgressBar();
    readonly Label status = Ui.Text("", 9.5f, false, Ui.Muted);
    readonly CheckBox startNow = new CheckBox();
    readonly TextBox terms = new TextBox();
    readonly CheckBox accept = new CheckBox();
    string state = "welcome";

    public InstallForm(Payload p, Options o)
    {
        payload = p; opts = o;
        folder = o.Folder ?? Program.InstalledFolder() ?? Program.DefaultFolder();
        Text = Program.AppName + (p.IsUpdate ? " Update" : " Setup");
        Icon = Ui.AppIcon();
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false; MinimizeBox = true;
        StartPosition = FormStartPosition.CenterScreen;
        BackColor = Ui.Back;
        Font = new Font("Segoe UI", 9.5f);
        AutoScaleMode = AutoScaleMode.Font;
        ClientSize = new Size(560, 380);

        var header = new Panel { Dock = DockStyle.Top, Height = 92, BackColor = Ui.Back };
        var pic = new PictureBox { Image = Ui.AppImage(), SizeMode = PictureBoxSizeMode.Zoom,
                                   Location = new Point(28, 22), Size = new Size(52, 52) };
        var eyebrow = Ui.Text(Program.AppName.ToUpperInvariant(), 8f, true, Ui.Accent);
        eyebrow.Location = new Point(96, 24); eyebrow.Size = new Size(420, 18);
        var title = Ui.Text("Dictation that stays on this PC", 15f, true, Ui.Ink);
        title.Location = new Point(94, 42); title.Size = new Size(440, 34);
        header.Controls.AddRange(new Control[] { pic, eyebrow, title });

        body.Location = new Point(28, 100); body.Size = new Size(504, 210); body.BackColor = Ui.Back;
        var footer = new Panel { Dock = DockStyle.Bottom, Height = 64, BackColor = Ui.Back };
        footer.Paint += (s, e) => e.Graphics.DrawLine(new Pen(Ui.Line), 0, 0, footer.Width, 0);
        primary.Location = new Point(ClientSize.Width - 28 - 120, 15);
        secondary.Location = new Point(ClientSize.Width - 28 - 120 - 10 - 120, 15);
        footer.Controls.AddRange(new Control[] { secondary, primary });
        Controls.AddRange(new Control[] { body, header, footer });
        primary.Click += OnPrimary;
        secondary.Click += (s, e) => Close();
        AcceptButton = primary;
        accept.CheckedChanged += (s, e) => { if (state == "licence") primary.Enabled = accept.Checked; };
        ShowWelcome();
    }

    // A full install asks the user to accept the licence terms (LICENSE-NOTICE.txt) first;
    // an update package does not. A silent install (/S) is taken as acceptance.
    bool AsksForLicence { get { return !payload.IsUpdate && payload.Notice != ""; } }

    void Lines(params Control[] controls)
    {
        body.Controls.Clear();
        int y = 0;
        foreach (var c in controls)
        {
            c.Location = new Point(0, y);
            c.Width = body.Width;
            if (c is Label)
            {
                var size = TextRenderer.MeasureText(c.Text, c.Font, new Size(body.Width, 1000), TextFormatFlags.WordBreak);
                c.Height = size.Height + 4;
            }
            body.Controls.Add(c);
            y += c.Height + 10;
        }
    }

    void ShowWelcome()
    {
        if (payload.IsUpdate)
        {
            string problem = Installer.UpdateProblem(payload, folder);
            if (problem != null)
            {
                state = "blocked";
                Lines(Ui.Text(problem, 10.5f, false, Ui.Ink));
                primary.Text = primary.AccessibleName = "Close";
                secondary.Visible = false;
                return;
            }
            Lines(
                Ui.Text("This updates " + Program.AppName + " to version " + payload.Version + ".", 10.5f, false, Ui.Ink),
                Ui.Text("Only the program itself changes: the speech model, your settings and your word lists stay " +
                        "as they are. Close MyTranscribe first if it is open.", 10f, false, Ui.Ink),
                Ui.Text("Updates " + folder, 9f, false, Ui.Muted));
            primary.Text = primary.AccessibleName = "Update";
            return;
        }
        bool update = Directory.Exists(folder);
        double gb = payload.UnpackedBytes / 1e9;
        Lines(
            Ui.Text(update
                ? "An earlier version is installed. Installing replaces it; your settings and word lists are kept."
                : "MyTranscribe turns what you say into text, on this PC: nothing you dictate is sent anywhere.",
                10.5f, false, Ui.Ink),
            Ui.Text("It installs for your Windows account only, so no administrator rights are needed, and adds a " +
                    "shortcut to your desktop and Start menu.", 10f, false, Ui.Ink),
            Ui.Text("Version " + payload.Version + "  ·  needs " + gb.ToString("0.0") + " GB of disk space\n" +
                    "Installs to " + folder, 9f, false, Ui.Muted));
        primary.Text = primary.AccessibleName = AsksForLicence ? "Next" : update ? "Update" : "Install";
    }

    void ShowLicence()
    {
        state = "licence";
        terms.Multiline = true; terms.ReadOnly = true; terms.ScrollBars = ScrollBars.Vertical;
        terms.BackColor = Color.White; terms.Font = new Font("Segoe UI", 9f); terms.Height = 152;
        terms.Text = payload.Notice.Replace("\r\n", "\n").Replace("\n", "\r\n");   // Windows line ends for the box
        terms.AccessibleName = "Licence terms";
        accept.Text = "I accept the licence terms";
        accept.AccessibleRole = AccessibleRole.CheckButton;
        accept.Font = new Font("Segoe UI", 10f);
        accept.Height = 28;
        Lines(terms, accept);
        primary.Text = primary.AccessibleName = Directory.Exists(folder) ? "Update" : "Install";
        primary.Enabled = accept.Checked;
        terms.Select(0, 0);
    }

    void OnPrimary(object sender, EventArgs e)
    {
        if (state == "welcome")
        {
            if (AsksForLicence) ShowLicence();
            else Begin();
        }
        else if (state == "licence") { if (accept.Checked) Begin(); }
        else if (state == "blocked") Close();
        else if (state == "done")
        {
            if (startNow.Checked) Installer.Start(folder);
            Close();
        }
    }

    void Begin()
    {
        state = "working";
        primary.Enabled = false; secondary.Enabled = false;
        bar.Height = 18; bar.Maximum = 1000;
        status.Text = "Copying files…";
        Lines(Ui.Text(payload.IsUpdate ? "Updating…" : "Installing…", 12f, true, Ui.Ink), bar, status);
        var worker = new Thread(() =>
        {
            Exception error = null;
            try
            {
                long last = 0;
                Action<long, long> progress = (done, total) =>
                {
                    if (done - last < (8 << 20) && done < total) return;
                    last = done;
                    BeginInvoke((Action)(() =>
                    {
                        bar.Value = (int)Math.Min(1000, 1000 * done / Math.Max(1, total));
                        status.Text = "Copying files… " + (done / 1e9).ToString("0.0") + " of " +
                                      (total / 1e9).ToString("0.0") + " GB";
                    }));
                };
                if (payload.IsUpdate) Installer.Update(payload, folder, progress);
                else Installer.Install(payload, folder, !opts.NoShortcuts, progress);
            }
            catch (Exception ex) { error = ex; }
            BeginInvoke((Action)(() => Finish(error)));
        });
        worker.IsBackground = true;
        worker.Start();
    }

    void Finish(Exception error)
    {
        if (error != null)
        {
            state = "welcome";
            primary.Enabled = true; secondary.Enabled = true;
            ShowWelcome();
            MessageBox.Show(error.Message, Program.AppName, MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }
        state = "done";
        startNow.Text = "Start MyTranscribe now";
        startNow.AccessibleRole = AccessibleRole.CheckButton;
        startNow.Checked = true;
        startNow.Font = new Font("Segoe UI", 10f);
        startNow.Height = 28;
        if (payload.IsUpdate)
            Lines(
                Ui.Text(Program.AppName + " is updated to version " + payload.Version + ".", 12f, true, Ui.Ink),
                Ui.Text("Start it as usual, from the shortcut on your desktop or from the Start menu.",
                        10f, false, Ui.Ink),
                startNow);
        else
            Lines(
                Ui.Text(Program.AppName + " is installed.", 12f, true, Ui.Ink),
                Ui.Text(opts.NoShortcuts ? "Start it from " + folder + "."
                        : "Start it from the shortcut on your desktop or from the Start menu. The first start asks " +
                          "a few questions to set it up (about three minutes).", 10f, false, Ui.Ink),
                startNow);
        primary.Text = primary.AccessibleName = "Finish";
        primary.Enabled = true;
        secondary.Visible = false;
    }
}

// ── Uninstalling ─────────────────────────────────────────────────────────────
static class Uninstaller
{
    public static int Run(Options o)
    {
        string folder = o.From ?? Path.GetDirectoryName(Application.ExecutablePath);
        string self = Application.ExecutablePath;
        // A program cannot delete the folder it runs from: run a copy from the temp folder.
        if (o.From == null)
        {
            string copy = Path.Combine(Path.GetTempPath(), "MyTranscribe-uninstall-" + Guid.NewGuid().ToString("N") + ".exe");
            File.Copy(self, copy);
            var args = "/uninstall /from=\"" + folder + "\" /parent=" + Process.GetCurrentProcess().Id + (o.Silent ? " /S" : "");
            Process.Start(new ProcessStartInfo(copy, args) { UseShellExecute = false });
            return 0;            // exit now: this program's own file is in the folder to be removed
        }
        if (o.Parent > 0)
        {
            try { Process.GetProcessById(o.Parent).WaitForExit(15000); }
            catch (ArgumentException) { }       // already gone
        }
        bool removeData = false;
        if (!o.Silent)
        {
            using (var f = new UninstallForm())
            {
                if (f.ShowDialog() != DialogResult.OK) { ScheduleDelete(self); return 1; }
                removeData = f.RemoveData;
            }
        }
        if (!File.Exists(Path.Combine(folder, "build_info.json")) || !File.Exists(Path.Combine(folder, Program.UninstallExe)))
        {
            Ui.Error("This does not look like a MyTranscribe folder, so nothing was removed: " + folder, o);
            ScheduleDelete(self);
            return 2;
        }
        try
        {
            Shortcuts.Remove();
            Installer.TryDelete(folder);
            if (Directory.Exists(folder))
                throw new IOException(Program.AppName + " is still running. Close it, then uninstall again.");
            Registry.CurrentUser.DeleteSubKeyTree(Program.RegKey, false);
            if (removeData)
            {
                Installer.TryDelete(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "MyTranscribe"));
                Installer.TryDelete(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "MyTranscribe"));
            }
            if (!o.Silent)
                MessageBox.Show(Program.AppName + " has been removed.", Program.AppName, MessageBoxButtons.OK, MessageBoxIcon.Information);
            return 0;
        }
        catch (Exception ex)
        {
            Ui.Error(ex.Message, o);
            return 1;
        }
        finally { ScheduleDelete(self); }
    }

    static void ScheduleDelete(string exe)
    {
        try
        {
            Process.Start(new ProcessStartInfo("cmd.exe", "/c ping 127.0.0.1 -n 3 > nul & del \"" + exe + "\"")
            {
                CreateNoWindow = true, UseShellExecute = false, WindowStyle = ProcessWindowStyle.Hidden
            });
        }
        catch (Exception) { }
    }
}

class UninstallForm : Form
{
    readonly CheckBox data = new CheckBox();
    public bool RemoveData { get { return data.Checked; } }

    public UninstallForm()
    {
        Text = "Remove " + Program.AppName;
        Icon = Ui.AppIcon();
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false; MinimizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;
        BackColor = Ui.Back;
        Font = new Font("Segoe UI", 9.5f);
        AutoScaleMode = AutoScaleMode.Font;
        ClientSize = new Size(460, 190);
        var q = Ui.Text("Remove " + Program.AppName + " from this PC?", 12f, true, Ui.Ink);
        q.Location = new Point(24, 20); q.Size = new Size(420, 28);
        data.Text = "Also remove my settings, word lists and log";
        data.Location = new Point(26, 64); data.Size = new Size(420, 26);
        var note = Ui.Text("Leave this unticked to keep them for a later install.", 9f, false, Ui.Muted);
        note.Location = new Point(44, 90); note.Size = new Size(400, 20);
        var ok = Ui.Button("Remove", true);
        var cancel = Ui.Button("Cancel", false);
        ok.Location = new Point(460 - 24 - 120, 136);
        cancel.Location = new Point(460 - 24 - 240 - 10, 136);
        ok.DialogResult = DialogResult.OK;
        cancel.DialogResult = DialogResult.Cancel;
        AcceptButton = ok; CancelButton = cancel;
        Controls.AddRange(new Control[] { q, data, note, ok, cancel });
    }
}
