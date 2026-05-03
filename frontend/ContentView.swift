//
//  ContentView.swift
//  ReelMind
//
//  Created by Deepti Jain on 01/05/26.
//

import SwiftUI
struct ContentView: View{
    var body: some View {
        VStack {
            @State var taskCount: Int = 0
            Image(systemName: "heart")
                .imageScale(.large)
                
            Text("You Go Girl 💕!")
            
        }
        .padding()
        
    }
}

#Preview {
    ContentView()
}

