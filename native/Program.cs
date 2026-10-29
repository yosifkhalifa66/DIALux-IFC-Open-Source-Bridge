using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.Loader;
using System.Text.Json;
using System.Windows;
using Dial.Compression.API;
using Dial.Dialux.App.Core;
using Dial.Dialux.App.Core.Services;
using Dial.Dialux.App.Core.Settings;
using Dial.Dialux.App.Utilities.Settings;
using Dial.Dialux.Classlib;
using Dial.Dialux.Classlib.Interfaces;
using Dial.Dialux.GeometryBase.GeometryManager;
using Dial.Dialux.GeometryRepresentationParams;
using Dial.Dialux.ModuleManager.Interfaces;
using Dial.Dialux.ModuleManager.Interfaces.Mediator;
using Dial.Dialux.NormData.Factory;
using Dial.Dialux.NormData.Interfaces;
using Dial.Dialux.Persistence.Factory;
using Dial.Dialux.Persistence.Interfaces;
using Dial.Dialux.PluginTypes.Interfaces;
using Dial.Dialux.ProductData.LuminaireDataInterfaces;
using Dial.Dialux.InteractionResultsHandling.Interfaces.SceneCalculation;
using Dial.Dialux.ProjectData.Factory;
using Dial.Dialux.ProjectData.Interfaces;
using Dial.Dialux.ProjectData.Interfaces.InstanceObjects;
using Dial.Dialux.ProjectData.Interfaces.Management;
using Dial.Dialux.ProjectData.Utilities;
using Dial.Dialux.ProjectDataService.Interfaces.Services;
using Dial.Dialux.PropertySets.Params;
using Dial.Dialux.Resources;
using Dial.Dialux.Resources.Interfaces;
using Dial.MathTypes;
using System.Windows.Media;

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        if ((args.Length != 4 || args[0] != "create") &&
            (args.Length != 3 || args[0] is not ("self-test" or "slab-test" or "inspect")))
        {
            Console.Error.WriteLine("Usage: DialuxIfcNativeHost create <model.json> <new-project.evo> <dialux-install> | self-test <new-project.evo> <dialux-install> | slab-test <new-project.evo> <dialux-install> | inspect <project.evo> <dialux-install>");
            return 2;
        }

        string install = Path.GetFullPath(args[0] == "create" ? args[3] : args[2]);
        string output = Path.GetFullPath(args[0] == "create" ? args[2] : args[1]);
        try
        {
            ConfigureAssemblyResolution(install);
            EnsureCompatibleVersion(install);
            using var host = NativeHost.Create(install, createProject: args[0] != "inspect");
            if (args[0] == "inspect")
            {
                Console.WriteLine(JsonSerializer.Serialize(NativeProjectReader.Load(host, output)));
                return 0;
            }

            if (args[0] == "slab-test")
                NativeModelBuilder.BuildSlabProbe(host);
            else
            {
                ModelPlan plan = args[0] == "self-test" ? ModelPlan.CreateExample() : ModelPlan.Read(args[1]);
                NativeModelBuilder.Build(host, plan);
                if (args[0] == "self-test")
                    NativeModelBuilder.AddTriangleMeshProbe(host);
            }
            NativeProjectWriter.Save(host, output);
            Console.WriteLine(JsonSerializer.Serialize(NativeModelBuilder.ReadBack(host)));
            return 0;
        }
        catch (Exception error)
        {
            while (error is TargetInvocationException { InnerException: not null } invocation)
                error = invocation.InnerException!;
            Console.Error.WriteLine($"{error.GetType().Name}: {error.Message}");
            return 1;
        }
    }

    private static void ConfigureAssemblyResolution(string install)
    {
        AssemblyLoadContext.Default.Resolving += (_, name) =>
        {
            string path = Path.Combine(install, name.Name + ".dll");
            return File.Exists(path) ? AssemblyLoadContext.Default.LoadFromAssemblyPath(path) : null;
        };
    }

    private static void EnsureCompatibleVersion(string install)
    {
        string assemblyPath = Path.Combine(install, "Dialux.ProjectData.Factory.dll");
        if (!File.Exists(assemblyPath))
            throw new DirectoryNotFoundException($"DIALux ProjectData factory was not found in '{install}'.");
        Version? version = AssemblyName.GetAssemblyName(assemblyPath).Version;
        if (version != new Version(5, 14, 0, 5))
            throw new NotSupportedException($"This native model adapter is verified for DIALux 5.14.0.5; detected {version}.");
    }
}

internal sealed class ModelPlan
{
    public required string ProjectName { get; init; }
    public SitePlan? Site { get; init; }
    public double WorkplaneM { get; init; } = 0.85;
    public required IReadOnlyList<StoreyPlan> Storeys { get; init; }
    public IReadOnlyList<NativeElementPlan> NativeElements { get; init; } = [];

    public static ModelPlan Read(string inputPath)
    {
        if (!File.Exists(inputPath))
            throw new FileNotFoundException("The native model input file does not exist.", inputPath);
        using JsonDocument document = JsonDocument.Parse(File.ReadAllText(inputPath));
        JsonElement root = document.RootElement;
        var storeys = new List<StoreyPlan>();
        var nativeElements = new List<NativeElementPlan>();
        foreach (JsonElement storey in root.GetProperty("storeys").EnumerateArray())
        {
            var rooms = new List<RoomPlan>();
            foreach (JsonElement room in storey.GetProperty("rooms").EnumerateArray())
            {
                var points = new List<Vector2D>();
                foreach (JsonElement point in room.GetProperty("contour").EnumerateArray())
                {
                    if (point.GetArrayLength() != 2)
                        throw new InvalidDataException("Room contour points must contain exactly two coordinates.");
                    points.Add(new Vector2D(point[0].GetDouble(), point[1].GetDouble()));
                }
                rooms.Add(new RoomPlan(
                    room.GetProperty("name").GetString() ?? throw new InvalidDataException("A room name is missing."),
                    points));
            }
            storeys.Add(new StoreyPlan(
                storey.GetProperty("name").GetString() ?? throw new InvalidDataException("A storey name is missing."),
                storey.GetProperty("elevation_m").GetDouble(),
                storey.GetProperty("height_m").GetDouble(),
                rooms));
        }
        if (root.TryGetProperty("native_elements", out JsonElement elements))
        foreach (JsonElement element in elements.EnumerateArray())
        {
            var triangles = new List<Vector3D[]>();
            foreach (JsonElement triangle in element.GetProperty("triangles").EnumerateArray())
            {
                if (triangle.GetArrayLength() != 3)
                    throw new InvalidDataException("Native mesh triangles must contain exactly three vertices.");
                triangles.Add(triangle.EnumerateArray().Select(point =>
                {
                    if (point.GetArrayLength() != 3) throw new InvalidDataException("Native mesh vertices must be XYZ triples.");
                    return new Vector3D(point[0].GetDouble(), point[1].GetDouble(), point[2].GetDouble());
                }).ToArray());
            }
            nativeElements.Add(new NativeElementPlan(
                element.GetProperty("name").GetString() ?? "IFC element",
                element.GetProperty("storey").GetString() ?? "",
                element.GetProperty("ifc_global_id").GetString() ?? "",
                element.GetProperty("ifc_type").GetString() ?? "IfcProduct",
                triangles));
        }

        return new ModelPlan
        {
            ProjectName = root.GetProperty("project_name").GetString() ?? "IFC Building",
            Site = root.TryGetProperty("site", out JsonElement site)
                ? new SitePlan(
                    site.GetProperty("location").GetString() ?? "IFC import location",
                    site.TryGetProperty("latitude_degrees", out JsonElement latitude) &&
                        latitude.ValueKind != JsonValueKind.Null
                        ? latitude.GetDouble()
                        : null,
                    site.TryGetProperty("longitude_degrees", out JsonElement longitude) &&
                        longitude.ValueKind != JsonValueKind.Null
                        ? longitude.GetDouble()
                        : null)
                : null,
            WorkplaneM = root.TryGetProperty("workplane_m", out JsonElement workplane)
                ? workplane.GetDouble()
                : 0.85,
            Storeys = storeys,
            NativeElements = nativeElements
        };
    }

    public static ModelPlan CreateExample() => new()
    {
        ProjectName = "Native Storey API Proof",
        WorkplaneM = 0.85,
        Storeys =
        [
            new StoreyPlan("Level 1", 0.0, 3.2,
            [
                new RoomPlan("Room 1A", [new(0, 0), new(5, 0), new(5, 4), new(0, 4)]),
                new RoomPlan("Room 1B", [new(5, 0), new(9, 0), new(9, 4), new(5, 4)])
            ]),
            new StoreyPlan("Level 2", 3.9624, 3.2,
            [
                new RoomPlan("Room 2A", [new(0, 0), new(5, 0), new(5, 4), new(0, 4)]),
                new RoomPlan("Room 2B", [new(5, 0), new(9, 0), new(9, 4), new(5, 4)])
            ])
        ]
    };
}

internal sealed record SitePlan(string Location, double? LatitudeDegrees, double? LongitudeDegrees);
internal sealed record StoreyPlan(string Name, double ElevationM, double HeightM, IReadOnlyList<RoomPlan> Rooms);
internal sealed record RoomPlan(string Name, IReadOnlyList<Vector2D> Contour);
internal sealed record NativeElementPlan(string Name, string Storey, string IfcGlobalId, string IfcType, IReadOnlyList<Vector3D[]> Triangles);

internal sealed class NativeHost : IDisposable
{
    public required ProjectDataModule ProjectModule { get; init; }
    public required ProjectDataServiceModule ServiceModule { get; init; }
    public required NormDataModule NormModule { get; init; }
    public required PersistenceModule PersistenceModule { get; init; }
    public required SettingsManager Settings { get; init; }
    public required InMemorySettingsStore SettingsStore { get; init; }
    public required StringResourceLookup Strings { get; init; }
    public required FilePathProvider Paths { get; init; }
    public required object LogInitializer { get; init; }
    public required nint ResultsManager { get; init; }

    public IProjectDataServices Services => ServiceModule.ProjectDataServices;

    public static NativeHost Create(string install, bool createProject)
    {
        string workspace = Path.Combine(Path.GetTempPath(), "DialuxIFCNative", Guid.NewGuid().ToString("N"));
        string temp = Path.Combine(workspace, "temp");
        Directory.CreateDirectory(temp);
        Environment.SetEnvironmentVariable("TEMP", temp);
        Environment.SetEnvironmentVariable("TMP", temp);
        _ = new Application { ShutdownMode = ShutdownMode.OnExplicitShutdown };

        var settingsStore = new InMemorySettingsStore();
        settingsStore.WriteString("Folders", "DIALuxProjectTemp", Path.Combine(workspace, "project-temp"));
        var paths = new FilePathProvider(
            install,
            settingsStore,
            folder => Path.Combine(workspace, "profile", folder.ToString()),
            isTesting: false);
        var settings = new SettingsManager(paths, settingsStore);
        Dial.Binder.Factory.ForceStaticConstructor();
        var guiAssembly = Assembly.LoadFrom(Path.Combine(install, "DIALux_x64.dll"));
        Type logType = guiAssembly.GetType("Dial.Dialux.Gui.LogInitializer", throwOnError: true)!;
        object log = Activator.CreateInstance(
            logType,
            BindingFlags.Instance | BindingFlags.NonPublic,
            binder: null,
            args: [settings, paths, settingsStore],
            culture: null)!;
        logType.GetMethod("Start")!.Invoke(log, null);

        var resources = new StringResourceLookup(ResourceFactory.CreateApplicationResourceLookup());
        var outputResources = new StringResourceLookup(ResourceFactory.CreateOutputResourceLookup());
        Type languageType = guiAssembly.GetType("Dial.Dialux.Gui.Resources.LanguageManager", throwOnError: true)!;
        _ = Activator.CreateInstance(languageType, [settings, paths, resources, outputResources, null]);
        var norm = new NormDataModuleFactory().Create(settingsStore, paths, resources);

        Dial.Dialux.GeometryFactory.Factory.ForceStaticConstructor();
        Assembly[] assemblies = Dial.Dialux.ModuleManager.Assemblies.Collect(install, Dial.Binder.Factory.CppDirectory);
        var persistence = new PersistenceModuleFactory().Create(
            Dial.Dialux.Persistence.Factory.Create.ConversionServiceFactory,
            paths,
            settingsStore,
            assemblies);

        var projectStatus = new Mediator<ProjectStatus>();
        var transactionStatus = new Mediator<TransactionStatus>();
        var changes = new Mediator<IChange>();
        var userLog = new Mediator<IProjectDataUserLogMessage>();
        var sceneCalculation = new Mediator<ISceneCalculationNotification>();
        nint results = Dial.Dialux.ResultsInterpreter.Factory.ResultsManagerFactory.Create();
        var productSource = new EmptyProductDataSource();
        var project = new ProjectDataModuleFactory().Create(
            resources,
            outputResources,
            norm.NormDataService,
            settings,
            paths,
            settingsStore,
            new ProgressHelper(),
            results,
            productSource,
            persistence.PersistenceFactory,
            projectStatus,
            transactionStatus,
            changes,
            userLog);
        var services = new ProjectDataServiceModuleFactory().Create(
            settings,
            paths,
            resources,
            project.ProjectMgr,
            project.GeometryMgr,
            persistence.PersistenceFactory,
            results,
            0.5,
            project.ObjectMgr,
            norm.NormDataService,
            norm.ObtrusiveLightStandardData,
            changes,
            projectStatus,
            transactionStatus,
            sceneCalculation);

        var modules = Dial.Dialux.ModuleManager.ModuleManager.Instance;
        modules.RegisterModule(norm, ModuleOrder.NormData);
        modules.RegisterModule(project, ModuleOrder.ProjectData);
        modules.RegisterModule(services, ModuleOrder.ProjectDataService);
        modules.DelayedModuleInit(null);
        if (createProject)
            project.ProjectMgr.CreateProject(new ProjectInfoParams());

        return new NativeHost
        {
            ProjectModule = project,
            ServiceModule = services,
            NormModule = norm,
            PersistenceModule = persistence,
            Settings = settings,
            SettingsStore = settingsStore,
            Strings = resources,
            Paths = paths,
            LogInitializer = log,
            ResultsManager = results
        };
    }

    public void Dispose()
    {
        try
        {
            if (ProjectModule.ProjectMgr.Project != null)
            {
                ProjectModule.ProjectMgr.BeginCloseProject();
                try { ProjectModule.ProjectMgr.CloseProject(); }
                finally { ProjectModule.ProjectMgr.EndCloseProject(); }
            }
        }
        finally
        {
            try { Dial.Dialux.ModuleManager.ModuleManager.Instance.DeinitializeModules(); }
            finally { LogInitializer.GetType().GetMethod("End")!.Invoke(LogInitializer, null); }
        }
    }
}

internal static class NativeProjectReader
{
    public static object Load(NativeHost host, string path)
    {
        var archive = new FileInfo(path);
        if (!archive.Exists || !archive.Extension.Equals(".evo", StringComparison.OrdinalIgnoreCase))
            throw new FileNotFoundException("Choose an existing DIALux .evo project.", path);

        var manager = host.ProjectModule.ProjectMgr;
        manager.InitProjectTempDirectories();
        manager.ProjectFilePath = archive.FullName;
        ArchiveReturn unpacked;
        using (new ResultsArchiveUnlockHelper(host.ProjectModule.GeometryResultsMgr))
        {
            unpacked = ProjectTempFolderManager.ProjectTempFolderMgr.UnZipProject(
                archive,
                manager.ProgressMgr).Item1;
        }
        if (unpacked.State != ResultState.NoError)
            throw new InvalidDataException($"DIALux could not unpack the project: {unpacked.State} {unpacked.Text}");
        MethodInfo loadMethod = manager.GetType().GetMethods()
            .Single(method => method.Name == "Load" && method.GetParameters().Length == 1);
        Type loadType = loadMethod.GetParameters()[0].ParameterType;
        object loadMode = Enum.Parse(loadType, "LoadProjectWithSerialisedGeometry");
        object loaded = loadMethod.Invoke(manager, [loadMode])
            ?? throw new InvalidDataException("DIALux returned no native project load result.");
        bool loadFailed = (bool)loaded.GetType().GetProperty("IsAnyError")!.GetValue(loaded)!;
        bool wasLoaded = (bool)loaded.GetType().GetProperty("IsLoaded")!.GetValue(loaded)!;
        if (loadFailed || !wasLoaded)
            throw new InvalidDataException($"DIALux could not reload the native project: {loaded}");
        return NativeModelBuilder.ReadBack(host);
    }
}

internal sealed class EmptyProductDataSource : ILuminaireProductDataSource
{
    public ImageSource GetVendorIconFromLuminaire(ILuminaireType luminaire) => throw new NotSupportedException();
    public ImageSource GetVendorIconFromLamp(ILampType lamp) => throw new NotSupportedException();
    public string GetProductDisplayNameFromManufName(string manufName, int lcid, PlugInType piType) => manufName;
    public ImageSource GetVendorIconFromManufacturerName(string manufacturer, int lcid, PlugInType plugInType) =>
        throw new NotSupportedException();
}

internal static class NativeModelBuilder
{
    public static void AddTriangleMeshProbe(NativeHost host)
    {
        Vector3D[] points =
        [
            new(0, 0, 0), new(1, 0, 0), new(1, 1, 0), new(0, 1, 0),
            new(0, 0, 1), new(1, 0, 1), new(1, 1, 1), new(0, 1, 1)
        ];
        int[][] triangles =
        [
            [0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
            [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5],
            [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]
        ];
        var surfaces = triangles.Select(indices =>
            (Dial.Dialux.GeometryRepresentationParams.Interfaces.ISurface3DParams)
            new Surface3DParams(indices.Select(index => points[index]).ToList(), UserDefaultMaterials.DefaultWallMaterial))
            .ToList();
        var geometry = new Surface3DCollectionParams(surfaces);
        Type productParamsType = Type.GetType(
            "Dial.Dialux.ProjectData.Utilities.InstanceProductParams, Dialux.ProjectData.Utilities",
            throwOnError: true)!;
        object parameters = Activator.CreateInstance(productParamsType, typeof(IGenericGeometryElement), geometry)
            ?? throw new InvalidOperationException("Could not create native arbitrary-geometry parameters.");
        productParamsType.GetProperty("CoordSys")!.SetValue(parameters, CoordSys3D.Default);
        IStorey storey = host.ProjectModule.ProjectMgr.Project!.Sites.SelectMany(site => site.Buildings)
            .SelectMany(building => building.Storeys).First();
        IInstanceProductParams instanceParameters = (IInstanceProductParams)parameters;
        storey.CreateContainedElement(instanceParameters, false).ObjectName = "Native Triangle Mesh Probe";
    }

    public static void BuildSlabProbe(NativeHost host)
    {
        var energy = new EnergyPerformanceTachometerParams
        {
            CurrencyUnit = host.Settings.CalculationSettings.EnergyPerformanceCurrencyUnit,
            PricePerKwh = host.Settings.CalculationSettings.EnergyPerformancePricePerKwh,
            Co2EmissionFactor = host.Settings.CalculationSettings.Co2EmissionFactor
        };
        var site = host.Services.ProjectOperations.CreateSite(
            host.NormModule.NormDataService.GetSiteUtilisationProfile(),
            host.NormModule.NormDataService.CommonUtilisationSettings,
            host.NormModule.NormDataService.GetMaintenancePreset(),
            energy,
            host.NormModule.ObtrusiveLightStandardData.GetUserDefaultValues())
            ?? throw new InvalidOperationException("DIALux did not create the native site.");
        site.Location = "Native floor slab API probe";
        site.TimeZone ??= TimeZoneInfo.Local;

        IBuilding building = host.Services.SpatialStructureOperations.CreateBuildingWithMultipleStoreys(
            site,
            CoordSys3D.Default,
            [new Vector2D(0, 0), new Vector2D(8, 0), new Vector2D(8, 6), new Vector2D(0, 6)],
            storeyCount: 2,
            buildingHeight: 6.0,
            floorSlabThickness: 0.2,
            UserDefaultMaterials.DefaultCeilingMaterial,
            UserDefaultMaterials.DefaultWallMaterial,
            UserDefaultMaterials.DefaultFloorMaterial)
            ?? throw new InvalidOperationException("DIALux did not create the slab-probe building.");
        building.ObjectName = "Native Floor Slab API Probe";
    }

    public static void Build(NativeHost host, ModelPlan plan)
    {
        Validate(plan);
        var energy = new EnergyPerformanceTachometerParams
        {
            CurrencyUnit = host.Settings.CalculationSettings.EnergyPerformanceCurrencyUnit,
            PricePerKwh = host.Settings.CalculationSettings.EnergyPerformancePricePerKwh,
            Co2EmissionFactor = host.Settings.CalculationSettings.Co2EmissionFactor
        };
        var site = host.Services.ProjectOperations.CreateSite(
            host.NormModule.NormDataService.GetSiteUtilisationProfile(),
            host.NormModule.NormDataService.CommonUtilisationSettings,
            host.NormModule.NormDataService.GetMaintenancePreset(),
            energy,
            host.NormModule.ObtrusiveLightStandardData.GetUserDefaultValues())
            ?? throw new InvalidOperationException("DIALux did not create the native site.");
        SitePlan sitePlan = plan.Site ?? new SitePlan("IFC import location", null, null);
        site.Location = sitePlan.Location;
        if (sitePlan.LatitudeDegrees is double latitude)
            site.Latitude = latitude * Math.PI / 180.0;
        if (sitePlan.LongitudeDegrees is double longitude)
            site.Longitude = longitude * Math.PI / 180.0;
        site.TimeZone ??= TimeZoneInfo.Local;

        IBuilding building = host.Services.SpatialStructureOperations.CreateEmptyBuilding(
            site,
            CoordSys3D.Default,
            plan.ProjectName)
            ?? throw new InvalidOperationException("DIALux did not create the native building.");
        ICommonUtilisationProfileData profile = host.NormModule.NormDataService.GetSiteUtilisationProfile();
        var sourceIds = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (StoreyPlan storeyPlan in plan.Storeys.OrderBy(item => item.ElevationM))
        {
            var storeyCoordinates = new CoordSys3D
            {
                Origin = new Vector3D(0, 0, storeyPlan.ElevationM)
            };
            IStorey storey = host.Services.SpatialStructureOperations.CreateEmptyStorey(
                building,
                storeyPlan.HeightM,
                storeyCoordinates,
                storeyPlan.Name)
                ?? throw new InvalidOperationException($"DIALux did not create storey '{storeyPlan.Name}'.");

            foreach (RoomPlan roomPlan in storeyPlan.Rooms)
            {
                IStoreyContour contour = host.Services.SpatialStructureOperations.AddInnerContour(
                    storey,
                    roomPlan.Contour,
                    profile,
                    createWorkplane: true,
                    workplaneHeight: plan.WorkplaneM,
                    workplaneWallZone: 0.5,
                    textHeight: 0.25,
                    UserDefaultMaterials.DefaultTextMaterial,
                    UserDefaultMaterials.DefaultCeilingMaterial,
                    UserDefaultMaterials.DefaultWallMaterial,
                    UserDefaultMaterials.DefaultFloorMaterial)
                    ?? throw new InvalidOperationException(
                        $"DIALux did not create room '{roomPlan.Name}' on storey '{storeyPlan.Name}'.");
                ISpace space = contour.AssociatedSpace
                    ?? throw new InvalidOperationException(
                        $"DIALux created no native space for room '{roomPlan.Name}'.");
                string uniqueName = MakeUniqueName(roomPlan.Name, sourceIds);
                space.ObjectName = uniqueName;
            }
            foreach (NativeElementPlan element in plan.NativeElements.Where(item => item.Storey == storeyPlan.Name))
            {
                var surfaces = element.Triangles.Select(triangle =>
                    (Dial.Dialux.GeometryRepresentationParams.Interfaces.ISurface3DParams)
                    new Surface3DParams(triangle.ToList(), UserDefaultMaterials.DefaultWallMaterial)).ToList();
                var geometry = new Surface3DCollectionParams(surfaces);
                Type paramsType = Type.GetType("Dial.Dialux.ProjectData.Utilities.InstanceProductParams, Dialux.ProjectData.Utilities", true)!;
                object rawParams = Activator.CreateInstance(paramsType, typeof(IGenericGeometryElement), geometry)
                    ?? throw new InvalidOperationException("Could not create native IFC mesh parameters.");
                paramsType.GetProperty("CoordSys")!.SetValue(rawParams, CoordSys3D.Default);
                var instanceParams = (IInstanceProductParams)rawParams;
                IGenericGeometryElement native = (IGenericGeometryElement)storey.CreateContainedElement(instanceParams, false);
                native.ObjectName = element.Name.Length > 80 ? element.Name[..80] : element.Name;
            }
        }
    }

    public static object ReadBack(NativeHost host)
    {
        var site = host.ProjectModule.ProjectMgr.Project!.Sites.Single();
        var buildings = site.Buildings.Select(building => new
        {
            name = building.ObjectName,
            storeys = building.Storeys.Select(storey => new
            {
                name = storey.ObjectName,
                elevation_m = storey.WorldCoordSys.Origin.Z,
                height_m = storey.Height,
                rooms = storey.Spaces.Select(space => space.ObjectName).ToArray(),
                room_floor_elevations_m = storey.Spaces.Select(space => space.WorldCoordSys.Origin.Z).ToArray(),
                contained_elements = storey.ContainedElements.Select(element => new
                {
                    name = element.ObjectName,
                    native_type = element.GetType().Name,
                    is_generic_geometry = element is IGenericGeometryElement
                }).ToArray(),
                storey_elements = storey.StoreyElements.Select(element => new
                {
                    name = element.ObjectName,
                    native_type = element.GetType().Name,
                    contour_count = element.Contours.Count(),
                    associated_space_count = element.Contours
                        .Select(contour => contour.AssociatedSpace)
                        .Where(space => space is not null)
                        .Distinct()
                        .Count()
                }).ToArray(),
                floors = storey.Floors.Select(slab => new
                {
                    name = slab.ObjectName,
                    native_type = slab.GetType().Name,
                    is_defined_by_contour = slab.IsDefinedByContour
                }).ToArray(),
                ceilings = storey.Ceilings.Select(slab => new
                {
                    name = slab.ObjectName,
                    native_type = slab.GetType().Name,
                    is_defined_by_contour = slab.IsDefinedByContour
                }).ToArray(),
                room_surfaces = storey.Spaces.Select(space => new
                {
                    name = space.ObjectName,
                    surface_element_count = space.RoomMainSurfaceElements.Count(),
                    opening_count = space.ContainedBuildingOpenings.Count(),
                    space_opening_count = space.SpaceOpenings.Count()
                }).ToArray()
            }).ToArray()
        }).ToArray();
        return new
        {
            location = site.Location,
            latitude_degrees = site.Latitude * 180.0 / Math.PI,
            longitude_degrees = site.Longitude * 180.0 / Math.PI,
            native_counts = new
            {
                building_count = site.Buildings.Count(),
                storey_count = site.Buildings.Sum(building => building.Storeys.Count()),
                room_count = site.Buildings.SelectMany(building => building.Storeys).Sum(storey => storey.Spaces.Count()),
                generic_geometry_element_count = site.Buildings.SelectMany(building => building.Storeys)
                    .Sum(storey => storey.ContainedElements.OfType<IGenericGeometryElement>().Count()),
                boundary_element_count = site.Buildings.SelectMany(building => building.Storeys).Sum(storey => storey.StoreyElements.Count()),
                boundary_contour_count = site.Buildings.SelectMany(building => building.Storeys)
                    .Sum(storey => storey.StoreyElements.Sum(element => element.Contours.Count())),
                floor_slab_count = site.Buildings.SelectMany(building => building.Storeys).Sum(storey => storey.Floors.Count()),
                ceiling_slab_count = site.Buildings.SelectMany(building => building.Storeys).Sum(storey => storey.Ceilings.Count()),
                room_opening_count = site.Buildings.SelectMany(building => building.Storeys).SelectMany(storey => storey.Spaces)
                    .Sum(space => space.ContainedBuildingOpenings.Count())
            },
            time_zone_id = site.TimeZone.Id,
            buildings
        };
    }

    private static void Validate(ModelPlan plan)
    {
        if (string.IsNullOrWhiteSpace(plan.ProjectName))
            throw new InvalidDataException("The project name cannot be blank.");
        if (plan.Site is SitePlan site &&
            (string.IsNullOrWhiteSpace(site.Location) ||
             (site.LatitudeDegrees is double latitude &&
              (!double.IsFinite(latitude) || latitude is < -90 or > 90)) ||
             (site.LongitudeDegrees is double longitude &&
              (!double.IsFinite(longitude) || longitude is < -180 or > 180))))
            throw new InvalidDataException("The IFC site location or coordinates are invalid.");
        if (!double.IsFinite(plan.WorkplaneM) || plan.WorkplaneM <= 0)
            throw new InvalidDataException("The workplane height must be a finite value greater than zero.");
        if (plan.Storeys.Count == 0)
            throw new InvalidDataException("The IFC contains no selected storeys with rooms.");
        foreach (StoreyPlan storey in plan.Storeys)
        {
            if (string.IsNullOrWhiteSpace(storey.Name) || !double.IsFinite(storey.ElevationM) ||
                !double.IsFinite(storey.HeightM) || storey.HeightM <= 0)
                throw new InvalidDataException($"Storey '{storey.Name}' has an invalid name, elevation, or height.");
            if (storey.Rooms.Count == 0)
                throw new InvalidDataException($"Storey '{storey.Name}' contains no rooms.");
            foreach (RoomPlan room in storey.Rooms)
            {
                if (string.IsNullOrWhiteSpace(room.Name) || room.Contour.Count < 3)
                    throw new InvalidDataException($"Storey '{storey.Name}' contains an invalid room.");
                if (room.Contour.Any(point => !double.IsFinite(point.X) || !double.IsFinite(point.Y)))
                    throw new InvalidDataException($"Room '{room.Name}' contains a non-finite coordinate.");
            }
        }
    }

    private static string MakeUniqueName(string name, HashSet<string> existing)
    {
        string baseName = name.Trim();
        if (baseName.Length == 0)
            baseName = "Room";
        string candidate = baseName;
        int suffix = 2;
        while (!existing.Add(candidate))
        {
            candidate = $"{baseName} ({suffix})";
            suffix++;
        }
        return candidate;
    }
}

internal static class NativeProjectWriter
{
    public static void Save(NativeHost host, string outputPath)
    {
        var output = new FileInfo(outputPath);
        if (!output.Extension.Equals(".evo", StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("The output must use the .evo extension.", nameof(outputPath));
        if (output.Exists)
            throw new IOException($"Refusing to overwrite an existing DIALux project: {output.FullName}");
        output.Directory!.Create();

        string temporary = Path.Combine(output.DirectoryName!, Guid.NewGuid().ToString("N") + ".evo");
        var manager = host.ProjectModule.ProjectMgr;
        string previousPath = manager.ProjectFilePath;
        bool saved = false;
        try
        {
            manager.ProjectFilePath = output.FullName;
            Type archiveFactory = Assembly.Load("Dialux.InteractionFileHandling")
                .GetType("Dial.Dialux.InteractionFileHandling.LoadSave.ArchiveInfoFactory", throwOnError: true)!;
            MethodInfo createArchiveInfo = archiveFactory.GetMethod(
                "CreateArchiveInfo",
                BindingFlags.Static | BindingFlags.NonPublic)
                ?? throw new MissingMethodException(archiveFactory.FullName, "CreateArchiveInfo");
            object archiveInfo = createArchiveInfo.Invoke(null, [null, manager])
                ?? throw new InvalidOperationException("DIALux did not create archive metadata.");
            MethodInfo createPersistenceInfos = host.PersistenceModule.PersistenceFactory.GetType()
                .GetMethods(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)
                .Single(method =>
                {
                    if (method.Name != "CreatePersistenceInfos")
                        return false;
                    ParameterInfo[] parameters = method.GetParameters();
                    return parameters.Length == 3 && parameters[0].ParameterType.IsInstanceOfType(archiveInfo);
                });
            object persistenceInfos = createPersistenceInfos
                .Invoke(host.PersistenceModule.PersistenceFactory, [archiveInfo, output.Name, false])
                ?? throw new InvalidOperationException("DIALux did not create persistence metadata.");
            if (!manager.Save((IPersistenceInfos)persistenceInfos))
                throw new InvalidOperationException("DIALux ProjectManager.Save failed.");
            _ = DesktopPersistence.SaveModules(host);

            Type folderType = Assembly.Load("Dialux.Classlib")
                .GetType("Dial.Dialux.Classlib.ProjectTempFolderManager", throwOnError: true)!;
            object folderManager = folderType.GetProperty(
                "ProjectTempFolderMgr",
                BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic)!.GetValue(null)!;
            string projectTempFolder = (string)folderType.GetProperty(
                "ProjectTempFolder",
                BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!.GetValue(folderManager)!;
            object zipResult;
            using (new ResultsArchiveUnlockHelper(host.ProjectModule.GeometryResultsMgr))
            {
                folderType.GetMethod("WriteArchiveInfo")!.Invoke(folderManager, [archiveInfo, projectTempFolder]);
                zipResult = folderType.GetMethod("ZipProject")!.Invoke(
                    folderManager,
                    [new FileInfo(temporary), manager.ProgressMgr])!;
            }
            string? zipState = zipResult.GetType().GetProperty("State")?.GetValue(zipResult)?.ToString();
            if (zipState != "NoError")
            {
                string? zipText = zipResult.GetType().GetProperty("Text")?.GetValue(zipResult)?.ToString();
                throw new IOException($"DIALux could not package the new project: {zipState} {zipText}");
            }
            File.Move(temporary, output.FullName, overwrite: false);
            saved = true;
        }
        finally
        {
            if (!saved)
                manager.ProjectFilePath = previousPath;
            if (File.Exists(temporary))
                File.Delete(temporary);
        }
    }
}
