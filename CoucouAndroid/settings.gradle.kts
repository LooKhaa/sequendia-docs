pluginManagement {
    includeBuild("../")
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
rootProject.name = "CoucouAndroid"
include(":app")
