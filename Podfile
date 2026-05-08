platform :ios, '14.0'

target 'ReelMind' do
  use_frameworks!

  pod 'Firebase/Analytics'
  pod 'Firebase/Messaging'

end


post_install do |installer|
  installer.pods_project.targets.each do |target|
    target.build_configurations.each do |config|
      config.build_settings['IPHONEOS_DEPLOYMENT_TARGET'] = '14.0'
      config.build_settings['ENABLE_USER_SCRIPT_SANDBOXING'] = 'NO'
    end
  end
end
