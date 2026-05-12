//
//  ContentView.swift
//  ReelMind
//
//  Created by Deepti Jain on 01/05/26.
//

import SwiftUI

struct ContentView: View {
    var body: some View {
        ReelsHomeView()
    }
}

#Preview {
    ContentView()
        .environmentObject(AuthSession())
}
