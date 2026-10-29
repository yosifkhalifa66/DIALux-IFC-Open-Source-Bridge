using System.Collections;
using System.IO;
using System.Linq.Expressions;
using System.Reflection;
using Dial.Dialux.Classlib;
using Dial.Dialux.Persistence.Interfaces;

internal static class DesktopPersistence
{
    private const BindingFlags Instance = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;

    internal static object CreateLoadSaveManager(NativeHost host)
    {
        var module = host.ProjectModule;
        var persistence = host.PersistenceModule.PersistenceFactory;
        object manager = Create(
            "Dialux.InteractionFileHandling",
            "Dial.Dialux.InteractionFileHandling.LoadSave.LoadSaveManager",
            persistence,
            host.Settings,
            module.ProjectMgr,
            module.ObjectMgr,
            module.ChangeMgr,
            module.ProgressMgr,
            module.GeometryMgr,
            module.GeometryResultsMgr,
            host.ServiceModule.ProductTracking);
        object helperFactory = Create(
            "Dialux.InteractionFileHandling",
            "Dial.Dialux.InteractionFileHandling.LoadSave.LoadExistingObjectHelperFactory");

        object output = Create(
            "Dialux.Output.Implementation",
            "Dial.Dialux.Output.Implementation.Base.OutputSettingsProvider",
            module.ObjectMgr,
            module.ChangeMgr,
            manager,
            host.Settings);
        output.GetType().GetMethod("InitXml")!.Invoke(output, null);

        object stf = Create(
            "Dialux.ImportStf",
            "Dial.Dialux.ImportStf.STF.StfManager",
            module.ProjectMgr,
            module.ObjectMgr,
            module.ChangeMgr,
            host.Services,
            persistence,
            host.Strings,
            host.Settings);
        stf.GetType().GetField("_loadExistingObjectHelperFactory", Instance)!.SetValue(stf, helperFactory);
        AddCallback(manager, "SaveModule", stf, "OnSaveModule");
        AddCallback(manager, "LoadModule", stf, "OnLoadModule");

        object workspace = Create(
            "Dialux.InteractionWorkspaces",
            "Dial.Dialux.InteractionWorkspaces.ConstructionWorkspace");
        object mode = Create("Dialux.InteractionModes", "Dial.Dialux.InteractionModes.ProjectInfoMode");
        Type toolType = Type("Dialux.InteractionToolManagement", "Dial.Dialux.InteractionToolManagement.ToolManager");
        ConstructorInfo constructor = toolType.GetConstructors(Instance).Single(item => item.GetParameters().Length == 4);
        ParameterInfo[] parameters = constructor.GetParameters();
        object tools = constructor.Invoke(
        [
            host.Settings,
            null,
            ArrayFactory(parameters[2].ParameterType, workspace),
            ArrayFactory(parameters[3].ParameterType, mode)
        ]);
        ((IList)toolType.GetProperty("AllWorkspaces")!.GetValue(tools)!).Add(workspace);
        ((IList)toolType.GetProperty("AllModes")!.GetValue(tools)!).Add(mode);
        toolType.GetField("_activeWorkspace", Instance)!.SetValue(tools, workspace);
        toolType.GetProperty("ActiveMode")!.GetSetMethod(nonPublic: true)!.Invoke(tools, [mode]);

        Type connectionType = Type(
            "Dialux.InteractionWorkspaces",
            "Dial.Dialux.InteractionWorkspaces.ToolManagerConnection");
        Type closureType = connectionType.GetNestedTypes(BindingFlags.NonPublic).Single(type =>
            type.GetMethods(Instance).Any(method => method.Name.Contains("g__OnSaveModule|", StringComparison.Ordinal)));
        object connection = Activator.CreateInstance(closureType, nonPublic: true)!;
        closureType.GetField("toolManager", Instance)!.SetValue(connection, tools);
        closureType.GetField("loadExistingObjectHelperFactory", Instance)!.SetValue(connection, helperFactory);
        closureType.GetField("persistenceFactory", Instance)!.SetValue(connection, persistence);
        AddCallback(
            manager,
            "SaveModule",
            connection,
            closureType.GetMethods(Instance).Single(method =>
                method.Name.Contains("g__OnSaveModule|", StringComparison.Ordinal)).Name);
        AddCallback(
            manager,
            "LoadModule",
            connection,
            closureType.GetMethods(Instance).Single(method =>
                method.Name.Contains("g__OnLoadModule|", StringComparison.Ordinal)).Name);

        object visibility = Create(
            "Dialux.InteractionViewManager",
            "Dial.Dialux.InteractionViewManager.VisibilityManager.VisibilityManager");
        Type("Dialux.Interaction.Factory", "Dial.Dialux.Interaction.Factory.Factories.InteractionViewManagerModuleFactory")
            .GetMethod("ConnectToLoadSaveManager", BindingFlags.Static | BindingFlags.NonPublic)!
            .Invoke(null, [visibility, manager, helperFactory, persistence]);
        return manager;
    }

    internal static string[] SaveModules(NativeHost host)
    {
        object manager = CreateLoadSaveManager(host);
        var handlers = (Delegate?)manager.GetType().GetField("SaveModule", Instance)!.GetValue(manager)
            ?? throw new InvalidOperationException("DIALux desktop serializers were not registered.");
        IStorage storage = ProjectTempFolderManager.ProjectTempFolderMgr.GetArchiveStorage();
        var saved = new List<string>();
        foreach (Delegate handler in handlers.GetInvocationList())
        {
            var args = new LoadSaveEventArgs(storage, ArchiveInfo.Empty);
            handler.DynamicInvoke(manager, args);
            if (args.Result.IsAnyError)
                throw new IOException("DIALux desktop module save failed: " + handler.Method.DeclaringType?.FullName);
            saved.Add(handler.Method.DeclaringType!.FullName!);
        }
        return saved.ToArray();
    }

    private static Type Type(string assembly, string name) =>
        Assembly.Load(assembly).GetType(name, throwOnError: true)!;

    private static object Create(string assembly, string name, params object?[] arguments) =>
        Activator.CreateInstance(Type(assembly, name), Instance, binder: null, args: arguments, culture: null)!;

    private static Delegate ArrayFactory(Type factoryType, object value)
    {
        Type arrayType = factoryType.GenericTypeArguments.Single();
        Array array = Array.CreateInstance(arrayType.GetElementType()!, 1);
        array.SetValue(value, 0);
        return Expression.Lambda(factoryType, Expression.Constant(array, arrayType)).Compile();
    }

    private static void AddCallback(object manager, string eventName, object target, string methodName)
    {
        EventInfo eventInfo = manager.GetType().GetEvent(eventName)!;
        MethodInfo method = target.GetType().GetMethod(methodName, Instance)!;
        eventInfo.AddEventHandler(manager, method.CreateDelegate(eventInfo.EventHandlerType!, target));
    }
}
